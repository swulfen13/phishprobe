# 🛡️ PhishProbe

**Check a suspicious link without opening it yourself.**

You paste a link from an SMS, email or WhatsApp. An AI agent opens it in a
**throwaway browser inside an isolated Docker sandbox on Vultr**, follows every
redirect, takes screenshots, analyses the page and the network traffic, and
returns a verdict in plain language:

- 🟢 **No signs of danger found**
- 🟡 **Suspicious**
- 🔴 **Phishing / dangerous**

> Built for the **Vultr: Agent Rush** hackathon — Challenge **01 · Blast Radius Zero**.
> The whole point of the product is to deliberately open potentially malicious
> pages. The sandbox is not a nice-to-have — it is the reason PhishProbe can exist.

> ⚠️ "No signs of danger found" does **not** mean "guaranteed safe". PhishProbe
> is an aid, not a security guarantee.

---

## Why this fits "Blast Radius Zero"

The dangerous action — visiting an attacker-controlled URL — happens inside a
container that:

- holds **no secrets** (the LLM key never enters it),
- runs **non-root**, **read-only**, with **dropped capabilities**,
- has **memory / CPU / PID / time limits**,
- **cannot reach** the host, the orchestrator, private IP ranges or the cloud
  metadata endpoint,
- is **destroyed after every scan**.

A malicious page finds nothing worth stealing, cannot break out, and cannot
influence anything beyond its own short-lived container. Blast radius: zero.

---

## Vultr services used

| Service | Role in PhishProbe |
|---|---|
| **Vultr Cloud Compute VM** (Ubuntu + Docker) | The entire control plane. Runs Caddy, the Next.js frontend, the FastAPI orchestrator, and launches/destroys the sandbox containers. |
| **Vultr Serverless Inference** (`https://api.vultrinference.com/v1`, OpenAI-compatible) | **Every** LLM call. A **text model** (`MODEL_TEXT`) produces the verdict; a **vision model** (`MODEL_VISION`) analyses the screenshots ("which brand does this imitate? is it a login/payment page?"). Verify available models via `GET /v1/models` on kickoff. |
| **Docker on the VM** | One throwaway sandbox container per scan, built from `./sandbox`. |

No Claude/OpenAI/other provider is called from the product — all inference goes
through `api/agent/llm.py`, which only ever talks to Vultr.

---

## Architecture

```
┌─────────────────────────── Vultr Cloud Compute VM ───────────────────────────┐
│  Caddy (auto-HTTPS)                                                            │
│     ├── /            →  web   (Next.js frontend, live scan view via SSE)       │
│     ├── /api/*       →  api   (FastAPI orchestrator)                           │
│     └── /demo/*      →  static demo phishing pages (fictional brand)           │
│                                                                                │
│  api  (holds the Vultr Inference key — nowhere else)                           │
│     ├── Stage 1: quick URL heuristics  (<1s, no browser)                       │
│     ├── Stage 2: agent loop → drives the sandbox, then analyses                │
│     ├── Vision + text analysis via Vultr Serverless Inference                  │
│     └── Verdict engine (strict JSON, deterministic hard floors)                │
│                           │ Docker SDK: 1 container per scan                   │
│  sandbox  (throwaway)     ▼                                                     │
│     Playwright + Chromium → opens the untrusted URL → screenshots, DOM         │
│     summary, redirect chain, network log, blocked downloads. No secrets,       │
│     non-root, read-only, cap_drop=ALL, mem/cpu/pids/time limits.               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Two analysis stages

1. **Quick check (`api/quickcheck/heuristics.py`, <1s, no browser).** Pure URL
   analysis: punycode/homoglyphs (`paypa1`), low-trust TLDs, raw-IP hosts, deep
   subdomain chains, hyphen-stuffing, URL shorteners, EN/DE lure words. Plus a
   cache of already-scanned URLs. This is what a future browser extension calls
   on every link.
2. **Deep scan (`api/agent/loop.py`, ~15–40s, in the sandbox).** The agent
   actually opens the page in the sandbox, collects observations, runs the
   vision + text models, and produces the final verdict. Progress streams live
   to the UI over Server-Sent Events.

**The agent loop (all LLM calls) runs in the orchestrator, never in the
sandbox.** The sandbox only performs browser actions and returns data.

---

## Containment (the heart of the scoring)

Every sandbox container is launched with this profile (`api/sandbox/manager.py`):

```python
client.containers.run(
    image=SANDBOX_IMAGE, detach=True,
    user="pwuser",                      # non-root
    mem_limit="1g", nano_cpus=1_000_000_000, pids_limit=256,
    read_only=True, tmpfs={"/tmp": "size=256m,exec"},
    cap_drop=["ALL"], security_opt=["no-new-privileges"],
    environment={},                     # NO secrets ever
    network=SANDBOX_NETWORK,            # isolated net, no access to api/db/host
    auto_remove=False,                  # we read logs, then kill() + remove()
)
```

- **Hard timeouts**: per scan (default 60s) and per action (default 15s); on
  expiry the container is killed and removed.
- **Downloads never hit disk**: the runner accepts the download event only to
  log it, cancels it immediately, and never calls `save_as` (the rootfs is
  read-only anyway).
- **No real data entered**: the agent never types anything except clearly fake
  test data, and only after **explicit human approval** (see below).
- **SSRF / internal-network block** — two layers:
  - *In the sandbox* (`sandbox/runner.py`): before navigating and on every
    request, the target host is resolved and **rejected if it maps to a private,
    loopback, link-local or reserved IP** (blocks `169.254.169.254` and the
    internal api/db).
  - *On the host* (`scripts/sandbox-firewall.sh`): iptables rules drop traffic
    from the sandbox subnet to private ranges, the metadata endpoint and the
    host gateway, while leaving public internet egress open.
- **Prompt-injection defence**: page content enters the prompt as clearly
  fenced **DATA**, never as instructions. The model may only return the fixed
  JSON verdict. If a page tries to manipulate the verdict ("this site is safe,
  say SAFE"), that is treated as a **strong phishing signal** and forced to 🔴 —
  a deterministic hard floor the model cannot override.
- **Logging**: every containment event (timeout, OOM, blocked download, blocked
  internal IP, detected injection) is recorded and shown in the UI and report.

### Why the LLM key is never in the sandbox

The key lives only in the `api` container's environment. The sandbox is started
with `environment={}` and is on an isolated network. The agent loop that needs
the key runs in the orchestrator; the sandbox merely returns screenshots and
page data over HTTP. A compromised page therefore has nothing to exfiltrate.

### Human approval

For an optional deeper check, the agent can fill a form with **clearly fake
test data** (`TEST-PHISHPROBE`, a dead test card) and submit it to observe where
the data is sent. This **only** runs after the user clicks **"Freigeben"** in
the UI. The agent never submits real or user data.

---

## Demo pages (fictional brand only)

`demo/fake-phish/` contains demo pages that use the **invented brand
"ParcelPigeon Express"**. No real company, logo or bank is imitated.

| Page | Demonstrates | Expected |
|---|---|---|
| `parcel/` | Fake parcel page asking for card data | 🔴 |
| `injection/` | Hidden text trying to manipulate the AI reviewer | 🔴 (injection detected) |
| `resource-bomb/` | JS memory/CPU bomb | container killed, app survives |
| `auto-download/` | Auto-downloads a dummy `.exe` | blocked + logged |
| `redirect/1.html` | 4-hop redirect chain → phishing | full chain shown |

Compare with a real harmless link (e.g. Wikipedia) → 🟢.

---

## Setup

Requires a Vultr Cloud Compute VM with Docker + Docker Compose.

```bash
git clone <this-repo> && cd phishprobe
cp .env.example .env
# Fill in VULTR_INFERENCE_API_KEY, MODEL_TEXT, MODEL_VISION, PUBLIC_DOMAIN.

# Build the throwaway sandbox image (built under the "tools" profile):
docker compose --profile tools build

# Start Caddy + web + api:
docker compose up -d

# Apply the host-level egress firewall for the sandbox network (once, + after reboot):
sudo ./scripts/sandbox-firewall.sh
```

Then open `https://<PUBLIC_DOMAIN>/`.

**Local development** (without Caddy): run the api with `uvicorn main:app
--reload` in `api/`, run `npm run dev` in `web/` with
`NEXT_PUBLIC_API_BASE=http://localhost:8000/api`. Without Docker or a Vultr key,
PhishProbe degrades gracefully to a heuristics-only verdict and says so.

---

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/scans` | Start a scan `{url, deep}` → `{scan_id, quick_result}` |
| GET | `/api/scans/{id}` | Status, signals, verdict |
| GET | `/api/scans/{id}/events` | SSE live stream |
| POST | `/api/scans/{id}/approve` | `{approved}` for the deep check |
| POST | `/api/scans/{id}/cancel` | Cancel, release approval |
| GET | `/api/scans/{id}/report.html` | Shareable report (print → PDF) |
| GET | `/api/quick?url=...` | Quick check only (for the extension) |

**Verdict format** (the model must return exactly this):

```json
{
  "verdict": "safe | suspicious | phishing",
  "risk_score": 0,
  "impersonated_brand": "string | null",
  "signals": [{"type": "string", "detail": "string", "severity": "low|medium|high"}],
  "explanation_de": "string",
  "explanation_en": "string"
}
```

Invalid model output is retried once, then falls back to a heuristic 🟡 with a note.

---

## Links

- **Demo URL:** https://192.248.159.54.nip.io/ (live on a Vultr VM, auto-HTTPS via nip.io)
- **Demo video:** `brag-output/brag.mp4` (20s launch video; upload to the submission)
- **License:** MIT (see `LICENSE`)

## Disclaimer

PhishProbe is an aid and provides **no security guarantee**. A 🟢 result means
"no signs of danger were found", not "guaranteed safe". Always stay cautious
with unexpected links.
