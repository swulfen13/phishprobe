# PhishProbe Chrome Extension (MV3)

Two ways to use it:

**1. Manual** — right-click any link → **"Mit PhishProbe prüfen"**, or paste a
link into the toolbar popup. Runs the fast quick-check for an instant badge
(🟢/🟡/🔴) and starts a full deep scan in the Vultr sandbox, opening the result.

**2. Secure-Modus** (toggle in the popup) — every left-click on an http(s) link
is held back, run through the quick-check first, and **before the page loads** a
warning appears if the link looks suspicious or like phishing. You can then open
it in the sandbox, proceed anyway, or cancel.

> Scope of Secure-Modus: it intercepts link *clicks* (the main vector). It does
> not block typed address-bar navigations or purely programmatic redirects —
> MV3 has no synchronous "ask a server, then block" navigation hook.

## Install (developer mode)

1. Open `chrome://extensions`.
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select this `extension/` folder.
4. The 🛡️ PhishProbe icon appears in the toolbar.

## Server address

By default the extension talks to the public demo at
`https://192.248.159.54.nip.io`. To point it elsewhere, open the popup →
**Server-Adresse** and enter your own deployment URL (it is saved per browser).

The extension uses the same API as the web app (`/api/quick`, `/api/scans`),
so the LLM key stays on the server and never touches the browser.

> Icons are optional; Chrome shows a default icon if none are provided. Add
> `icon16/48/128.png` and an `"icons"` block to `manifest.json` for polish.
