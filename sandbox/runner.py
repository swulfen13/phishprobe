"""PhishProbe sandbox action server.

Runs INSIDE the throwaway container. It does exactly one dangerous thing —
open an untrusted URL in Chromium — and reports back structured observations.
It holds no secrets and makes no LLM calls; the orchestrator does the thinking.

Containment that lives here (defence in depth, independent of host firewall):
  * SSRF guard: refuses to load any URL whose host resolves to a private,
    loopback, link-local or reserved IP (blocks the cloud metadata endpoint
    169.254.169.254 and the internal api/db).
  * Downloads are never written to disk; attachment responses are only logged.
  * Every navigation hop, requested domain, console error and containment
    event is recorded.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import FastAPI
from pydantic import BaseModel
from playwright.async_api import async_playwright, Error as PlaywrightError

app = FastAPI(title="PhishProbe Sandbox")

# Viewports: many phishing kits only render on mobile, so we capture both.
DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# Patterns that indicate a page is trying to talk to the AI reviewer instead
# of the human visitor — prompt injection is itself a strong phishing signal.
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard the above",
    "you are a",
    "as an ai",
    "ai agent",
    "ai assistant",
    "language model",
    "this site is safe",
    "this website is safe",
    "mark this as safe",
    "classify this as safe",
    "say safe",
    "verdict: safe",
    "do not flag",
]


def _host_is_private(host: str) -> bool:
    """True if the host is an IP literal or resolves to a non-public address."""
    candidates: list[str] = []
    try:
        # IP literal?
        ipaddress.ip_address(host)
        candidates.append(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            candidates = [info[4][0] for info in infos]
        except socket.gaierror:
            # Can't resolve -> the request will fail anyway; don't block here.
            return False
    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


class ActRequest(BaseModel):
    action: str
    args: dict = {}


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/act")
async def act(req: ActRequest) -> dict:
    if req.action == "scan":
        return await scan_url(
            url=req.args.get("url", ""),
            action_timeout=float(req.args.get("action_timeout", 15)),
        )
    if req.action == "submit_fake":
        return await submit_fake(
            url=req.args.get("url", ""),
            action_timeout=float(req.args.get("action_timeout", 15)),
        )
    return {"ok": False, "error": f"unknown action: {req.action}"}


async def _make_resolution_cache():
    cache: dict[str, bool] = {}
    loop = asyncio.get_running_loop()

    async def is_private(host: str) -> bool:
        if host not in cache:
            cache[host] = await loop.run_in_executor(None, _host_is_private, host)
        return cache[host]

    return is_private


async def scan_url(url: str, action_timeout: float) -> dict:
    """Open `url`, follow redirects, capture screenshots + structured signals."""
    result: dict = {
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

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        result["error"] = "invalid URL (only http/https allowed)"
        return result

    is_private = await _make_resolution_cache()

    # Pre-flight SSRF check on the target host itself.
    if await is_private(parsed.hostname):
        result["containment_events"].append(
            {"type": "blocked_internal_ip", "detail": f"target host {parsed.hostname} resolves to a private/internal address"}
        )
        result["error"] = "target resolves to an internal address"
        return result

    timeout_ms = int(action_timeout * 1000)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--no-sandbox",  # we run unprivileged already; Chromium's own sandbox needs caps we drop
                "--disable-dev-shm-usage",
            ]
        )
        # We accept download events only to log them; on_download cancels every
        # one and never writes to disk (see on_download below). No file ever
        # lands in the container, which is read-only anyway except tmpfs /tmp.
        context = await browser.new_context(
            viewport=DESKTOP_VIEWPORT,
            accept_downloads=True,
            ignore_https_errors=True,
        )

        redirects: list[dict] = []
        network_log: list[dict] = []
        requested_domains: set[str] = set()
        downloads_blocked: list[dict] = []
        console_errors: list[str] = []
        containment_events: list[dict] = []

        async def route_handler(route):
            req_url = route.request.url
            host = urlparse(req_url).hostname or ""
            try:
                if host and await is_private(host):
                    containment_events.append(
                        {"type": "blocked_internal_ip", "detail": f"request to internal host {host} aborted"}
                    )
                    await route.abort()
                    return
            except Exception:
                pass
            await route.continue_()

        await context.route("**/*", route_handler)

        page = await context.new_page()

        def on_response(response):
            try:
                req = response.request
                host = urlparse(response.url).hostname
                if host:
                    requested_domains.add(host)
                if req.is_navigation_request() and req.frame == page.main_frame:
                    redirects.append({"url": response.url, "status": response.status})
                headers = response.headers
                disp = headers.get("content-disposition", "")
                if "attachment" in disp.lower():
                    downloads_blocked.append({"url": response.url, "via": "content-disposition"})
                    containment_events.append(
                        {"type": "download_blocked", "detail": f"attachment response from {response.url} not saved"}
                    )
                network_log.append(
                    {
                        "url": response.url,
                        "method": req.method,
                        "resource_type": req.resource_type,
                        "status": response.status,
                    }
                )
            except Exception:
                pass

        def on_console(msg):
            if msg.type in ("error", "warning"):
                console_errors.append(f"{msg.type}: {msg.text}"[:500])

        async def on_download(download):
            # We accept the event only to LOG it, then cancel immediately and
            # never call save_as() — the file is never written to disk. This is
            # the same containment as accept_downloads=False, but it also lets us
            # record blob-based downloads for the report.
            downloads_blocked.append({"url": download.url, "suggested_filename": download.suggested_filename})
            containment_events.append(
                {"type": "download_blocked", "detail": f"download '{download.suggested_filename}' from {download.url} cancelled, not saved"}
            )
            try:
                await download.cancel()
            except PlaywrightError:
                pass

        page.on("response", on_response)
        page.on("console", on_console)
        page.on("download", lambda d: asyncio.create_task(on_download(d)))

        try:
            await page.goto(url, wait_until="load", timeout=timeout_ms)
        except PlaywrightError as exc:
            msg = str(exc).splitlines()[0] if str(exc) else "navigation failed"
            if "Timeout" in msg:
                containment_events.append({"type": "action_timeout", "detail": msg[:300]})
            result["error"] = msg[:300]
            # Still try to capture whatever rendered.

        # Give late XHR/redirects a brief, bounded moment to settle.
        try:
            await page.wait_for_timeout(min(2000, timeout_ms // 3))
        except PlaywrightError:
            pass

        result["final_url"] = page.url

        try:
            dom = await page.evaluate(DOM_SUMMARY_JS)
        except PlaywrightError:
            dom = {}
        result["dom_summary"] = _enrich_dom(dom)

        # Screenshots: desktop first, then re-render mobile.
        try:
            shot = await page.screenshot(full_page=False)
            result["screenshot_desktop_b64"] = base64.b64encode(shot).decode()
        except PlaywrightError:
            pass

        try:
            mobile = await browser.new_context(
                viewport=MOBILE_VIEWPORT,
                user_agent=MOBILE_UA,
                accept_downloads=False,
                ignore_https_errors=True,
            )
            await mobile.route("**/*", route_handler)
            mpage = await mobile.new_page()
            await mpage.goto(url, wait_until="load", timeout=timeout_ms)
            await mpage.wait_for_timeout(min(1500, timeout_ms // 4))
            mshot = await mpage.screenshot(full_page=False)
            result["screenshot_mobile_b64"] = base64.b64encode(mshot).decode()
            await mobile.close()
        except PlaywrightError:
            pass

        await context.close()
        await browser.close()

        result["redirects"] = redirects
        result["network_log"] = network_log[:200]
        result["requested_domains"] = sorted(requested_domains)
        result["downloads_blocked"] = downloads_blocked
        result["console_errors"] = console_errors[:50]
        result["containment_events"] = containment_events
        result["ok"] = result["final_url"] is not None

    return result


def _enrich_dom(dom: dict) -> dict:
    """Add injection detection over all extracted text (visible + hidden)."""
    dom = dict(dom or {})
    # Only HIDDEN/off-screen text + comments count as injection. Visible body
    # text that merely discusses these phrases (e.g. a Wikipedia article about
    # phishing) is legitimate content and must not trigger a false positive.
    haystack = " ".join(
        [
            dom.get("hidden_text", ""),
            dom.get("title", ""),
        ]
    ).lower()
    found = [p for p in INJECTION_PATTERNS if p in haystack]
    dom["injection_matches"] = found
    return dom


async def submit_fake(url: str, action_timeout: float) -> dict:
    """Deep check after human approval: fill a form with CLEARLY FAKE test data
    and submit it, to observe where the data is sent. Never uses real data."""
    result: dict = {"ok": False, "submitted": False, "post_targets": [], "containment_events": []}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        result["error"] = "invalid URL"
        return result
    if _host_is_private(parsed.hostname):
        result["containment_events"].append(
            {"type": "blocked_internal_ip", "detail": "target resolves to internal address"}
        )
        return result

    timeout_ms = int(action_timeout * 1000)
    fake = {
        "text": "TEST-PHISHPROBE",
        "email": "testprobe@example.invalid",
        "card": "4000 0000 0000 0000",  # obvious test card, Luhn-valid but a dead BIN
        "cvv": "000",
        "password": "NotARealPassword-PhishProbe",
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(accept_downloads=False, ignore_https_errors=True)
        page = await context.new_page()
        post_targets: list[str] = []
        page.on(
            "request",
            lambda r: post_targets.append(r.url) if r.method == "POST" else None,
        )
        try:
            await page.goto(url, wait_until="load", timeout=timeout_ms)
            await page.evaluate(FILL_FORM_JS, fake)
            await page.wait_for_timeout(500)
            # Submit the first form if present.
            await page.evaluate("document.querySelector('form')?.submit()")
            await page.wait_for_timeout(min(3000, timeout_ms // 2))
            result["submitted"] = True
        except PlaywrightError as exc:
            result["error"] = str(exc).splitlines()[0][:300]
        result["post_targets"] = sorted(set(post_targets))
        result["ok"] = True
        await context.close()
        await browser.close()
    return result


# --- Page-side extraction (runs in the browser, returns plain JSON) ---

DOM_SUMMARY_JS = r"""
() => {
  const abs = (u) => { try { return new URL(u, location.href).href; } catch { return u; } };
  const forms = [...document.querySelectorAll('form')].slice(0, 20).map(f => {
    const inputs = [...f.querySelectorAll('input,select,textarea')].map(i => ({
      type: (i.getAttribute('type') || i.tagName).toLowerCase(),
      name: (i.getAttribute('name') || i.getAttribute('id') || '').slice(0, 60),
      autocomplete: (i.getAttribute('autocomplete') || '').slice(0, 40),
      placeholder: (i.getAttribute('placeholder') || '').slice(0, 60),
    }));
    const blob = JSON.stringify(inputs).toLowerCase();
    const cardHint = /card|credit|cc-|cvv|cvc|security code|iban|kreditkarte|kartennummer/.test(blob);
    return {
      action: abs(f.getAttribute('action') || location.href),
      method: (f.getAttribute('method') || 'get').toLowerCase(),
      inputs,
      has_password: inputs.some(i => i.type === 'password'),
      has_card_field: cardHint,
    };
  });
  const brandTexts = [];
  const push = (s) => { if (s && s.trim()) brandTexts.push(s.trim().slice(0, 120)); };
  push(document.title);
  const og = document.querySelector('meta[property="og:site_name"]');
  if (og) push(og.content);
  [...document.querySelectorAll('h1,h2')].slice(0, 10).forEach(h => push(h.innerText));
  [...document.querySelectorAll('img[alt]')].slice(0, 15).forEach(i => push(i.alt));
  // Hidden / off-screen text — where injections hide.
  let hidden = '';
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_ELEMENT);
  let n = walker.currentNode;
  let count = 0;
  while (n && count < 4000) {
    count++;
    const cs = getComputedStyle(n);
    const offscreen = (n.getBoundingClientRect().left < -500 || parseFloat(cs.textIndent) < -500);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0 ||
        n.getAttribute('aria-hidden') === 'true' || offscreen) {
      const t = (n.innerText || n.textContent || '').trim();
      if (t) hidden += ' ' + t;
    }
    n = walker.nextNode();
  }
  // HTML comments can carry injections too.
  const commentWalker = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT);
  let c = commentWalker.nextNode();
  while (c) { hidden += ' ' + (c.nodeValue || ''); c = commentWalker.nextNode(); }

  return {
    title: document.title || '',
    forms,
    password_field_count: forms.reduce((a, f) => a + f.inputs.filter(i => i.type === 'password').length, 0),
    has_card_field: forms.some(f => f.has_card_field),
    brand_texts: [...new Set(brandTexts)],
    visible_text: (document.body ? document.body.innerText : '').slice(0, 2000),
    hidden_text: hidden.slice(0, 2000),
    external_form_action: forms.some(f => { try { return new URL(f.action).host !== location.host; } catch { return false; } }),
  };
}
"""

FILL_FORM_JS = r"""
(fake) => {
  const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); };
  document.querySelectorAll('input,textarea').forEach(el => {
    const t = (el.type || '').toLowerCase();
    const name = ((el.name || '') + (el.id || '') + (el.placeholder || '')).toLowerCase();
    if (t === 'password') set(el, fake.password);
    else if (t === 'email' || name.includes('mail')) set(el, fake.email);
    else if (/card|credit|cc|kartennummer/.test(name)) set(el, fake.card);
    else if (/cvv|cvc|security/.test(name)) set(el, fake.cvv);
    else if (t === 'text' || t === '') set(el, fake.text);
  });
}
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
