"""Sandbox lifecycle manager. One throwaway container per scan, started with
the full containment profile from CLAUDE.md section 7, driven over HTTP, and
destroyed afterwards no matter what. Containment must never get weaker here.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import httpx

try:
    import docker
    from docker.errors import DockerException, NotFound
except ImportError:  # pragma: no cover - docker SDK missing in some dev setups
    docker = None
    DockerException = Exception
    NotFound = Exception


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


class SandboxUnavailable(RuntimeError):
    pass


_docker_client = None


def _client():
    global _docker_client
    if docker is None:
        raise SandboxUnavailable("docker SDK not installed")
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
            _docker_client.ping()
        except DockerException as exc:
            raise SandboxUnavailable(f"cannot reach Docker daemon: {exc}") from exc
    return _docker_client


def available() -> bool:
    try:
        _client()
        return True
    except SandboxUnavailable:
        return False


# --- containment profile ---------------------------------------------------

def _run_container():
    client = _client()
    return client.containers.run(
        image=_env("SANDBOX_IMAGE", "phishprobe-sandbox:latest"),
        detach=True,
        user="pwuser",                       # non-root
        mem_limit=_env("SANDBOX_MEM_LIMIT", "1g"),
        nano_cpus=int(_env("SANDBOX_NANO_CPUS", "1000000000")),  # 1 CPU
        pids_limit=int(_env("SANDBOX_PIDS_LIMIT", "256")),
        read_only=True,                      # immutable rootfs
        tmpfs={"/tmp": "size=256m,exec"},    # only writable area (Chromium needs exec)
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        environment={},                      # NO secrets ever reach the sandbox
        network=_env("SANDBOX_NETWORK", "phishprobe-sandbox-net"),
        auto_remove=False,                   # we clean up ourselves after reading logs
        labels={"app": "phishprobe", "role": "sandbox"},
    )


def _container_ip(container) -> Optional[str]:
    container.reload()
    nets = container.attrs.get("NetworkSettings", {}).get("Networks", {})
    for net in nets.values():
        ip = net.get("IPAddress")
        if ip:
            return ip
    return None


def _oom_killed(container) -> bool:
    try:
        container.reload()
        return bool(container.attrs.get("State", {}).get("OOMKilled"))
    except Exception:
        return False


def _destroy(container) -> None:
    """Kill + remove. Never raises — cleanup must always complete."""
    try:
        container.kill()
    except Exception:
        pass
    try:
        container.remove(force=True)
    except Exception:
        pass


# --- orchestration ----------------------------------------------------------

async def run_action(url: str, action: str = "scan") -> dict:
    """Start a sandbox, run one action under a hard timeout, destroy it."""
    if not available():
        raise SandboxUnavailable("Docker is not available on this host")

    loop = asyncio.get_running_loop()
    scan_timeout = float(_env("SCAN_TIMEOUT_SECONDS", "60"))
    action_timeout = float(_env("ACTION_TIMEOUT_SECONDS", "15"))
    containment_events: list[dict] = []

    container = await loop.run_in_executor(None, _run_container)
    started = time.monotonic()
    try:
        ip = await loop.run_in_executor(None, _container_ip, container)
        if not ip:
            raise SandboxUnavailable("sandbox container has no network address")
        base = f"http://{ip}:8080"

        await _wait_healthy(base, deadline=started + 20)

        async with httpx.AsyncClient(timeout=scan_timeout + 5) as http:
            try:
                resp = await asyncio.wait_for(
                    http.post(
                        f"{base}/act",
                        json={"action": action, "args": {"url": url, "action_timeout": action_timeout}},
                    ),
                    timeout=scan_timeout,
                )
                data = resp.json()
            except asyncio.TimeoutError:
                containment_events.append({"type": "scan_timeout", "detail": f"hard timeout after {scan_timeout:.0f}s, container killed"})
                data = _empty_result(url)
            except (httpx.HTTPError, ValueError) as exc:
                if _oom_killed(container):
                    containment_events.append({"type": "resource_limit", "detail": "container hit its memory limit (OOM) and was killed"})
                else:
                    containment_events.append({"type": "sandbox_error", "detail": str(exc)[:200]})
                data = _empty_result(url)

        if _oom_killed(container):
            containment_events.append({"type": "resource_limit", "detail": "container was OOM-killed during the scan"})

        data.setdefault("containment_events", [])
        data["containment_events"].extend(containment_events)
        data["sandbox_runtime_seconds"] = round(time.monotonic() - started, 1)
        return data
    finally:
        await loop.run_in_executor(None, _destroy, container)


async def _wait_healthy(base: str, deadline: float) -> None:
    async with httpx.AsyncClient(timeout=3) as http:
        while time.monotonic() < deadline:
            try:
                r = await http.get(f"{base}/health")
                if r.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.4)
    raise SandboxUnavailable("sandbox did not become healthy in time")


def _empty_result(url: str) -> dict:
    return {
        "ok": False,
        "requested_url": url,
        "final_url": None,
        "redirects": [],
        "screenshot_desktop_b64": None,
        "screenshot_mobile_b64": None,
        "dom_summary": {},
        "network_log": [],
        "requested_domains": [],
        "downloads_blocked": [],
        "console_errors": [],
        "containment_events": [],
    }
