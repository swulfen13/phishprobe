# PhishProbe Chrome Extension (MV3)

Right-click any link → **"Mit PhishProbe prüfen"**, or paste a link into the
toolbar popup. The extension runs the fast quick-check for an instant badge
(🟢/🟡/🔴) and starts a full deep scan in the Vultr sandbox, opening the live
result page.

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
