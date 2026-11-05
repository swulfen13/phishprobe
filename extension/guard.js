// Secure-mode guard (opt-in). When enabled, every left-click on an http(s)
// link is held back, run through the fast quick-check, and — if the link looks
// suspicious or like phishing — a warning is shown BEFORE the page loads.
//
// Scope note: this catches link clicks (the main vector). It cannot block
// typed address-bar navigations or purely programmatic redirects — MV3 has no
// synchronous "ask a server then block" navigation hook. Honest by design.

const DEFAULT_BASE = "https://192.248.159.54.nip.io";
let enabled = false;
let base = DEFAULT_BASE;

chrome.storage.sync.get(["secureMode", "apiBase"], (r) => {
  enabled = !!r.secureMode;
  base = (r.apiBase || DEFAULT_BASE).replace(/\/$/, "");
});
chrome.storage.onChanged.addListener((ch) => {
  if (ch.secureMode) enabled = ch.secureMode.newValue;
  if (ch.apiBase) base = (ch.apiBase.newValue || DEFAULT_BASE).replace(/\/$/, "");
});

document.addEventListener("click", onClick, true); // capture phase, before the page

async function onClick(e) {
  if (!enabled) return;
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest ? e.target.closest("a[href]") : null;
  if (!a || a.dataset.ppAllow === "1") { if (a) a.dataset.ppAllow = ""; return; }
  const href = a.href;
  if (!/^https?:/i.test(href)) return;
  try {
    const u = new URL(href);
    // ignore in-page anchor jumps
    if (u.origin === location.origin && u.pathname === location.pathname && u.hash) return;
  } catch { return; }

  e.preventDefault();
  e.stopPropagation();
  const level = await quick(href);
  if (level === "safe" || level === null) {
    proceed(a); // safe, or check failed -> don't hard-block
  } else {
    showWarning(href, level, a);
  }
}

async function quick(href) {
  try {
    const q = await fetch(`${base}/api/quick?url=${encodeURIComponent(href)}`).then((r) => r.json());
    return q.level;
  } catch {
    return null;
  }
}

function proceed(a) {
  a.dataset.ppAllow = "1"; // next synthetic click bypasses the guard
  a.click();
}

function showWarning(href, level, a) {
  const META = {
    suspicious: { emoji: "🟡", label: "Verdächtig", color: "#f59e0b" },
    phishing: { emoji: "🔴", label: "Phishing / gefährlich", color: "#ef4444" },
  };
  const m = META[level] || META.suspicious;
  const root = document.createElement("div");
  root.attachShadow({ mode: "open" });
  root.shadowRoot.innerHTML = `
    <div style="all:initial;position:fixed;inset:0;z-index:2147483647;display:flex;
      align-items:center;justify-content:center;background:rgba(2,6,23,.75);
      font-family:system-ui,Segoe UI,sans-serif">
      <div style="background:#111a2e;border:1px solid #1e2a44;border-radius:18px;max-width:520px;
        padding:28px 30px;box-shadow:0 30px 80px -20px #000;color:#e2e8f0">
        <div style="font-size:40px">${m.emoji}</div>
        <div style="font-size:21px;font-weight:700;color:${m.color};margin-top:6px">PhishProbe: ${m.label}</div>
        <p style="font-size:14px;color:#94a3b8;margin:10px 0 4px">Dieser Link wirkt im Schnell-Check auffällig:</p>
        <code style="display:block;word-break:break-all;background:#0b1120;border:1px solid #1e2a44;
          border-radius:8px;padding:8px 10px;font-size:12px;color:#cbd5e1">${escapeHtml(href)}</code>
        <div style="display:flex;gap:8px;margin-top:18px;flex-wrap:wrap">
          <button id="pp-scan" style="all:unset;cursor:pointer;background:#0ea5e9;color:#fff;font-weight:600;
            padding:10px 16px;border-radius:9px;font-size:14px">In Sandbox prüfen</button>
          <button id="pp-open" style="all:unset;cursor:pointer;border:1px solid #334155;color:#cbd5e1;
            padding:10px 16px;border-radius:9px;font-size:14px">Trotzdem öffnen</button>
          <button id="pp-cancel" style="all:unset;cursor:pointer;color:#64748b;padding:10px 12px;font-size:14px">Abbrechen</button>
        </div>
      </div>
    </div>`;
  document.documentElement.appendChild(root);
  const close = () => root.remove();
  root.shadowRoot.getElementById("pp-cancel").onclick = close;
  root.shadowRoot.getElementById("pp-open").onclick = () => { close(); proceed(a); };
  root.shadowRoot.getElementById("pp-scan").onclick = async () => {
    close();
    try {
      const res = await fetch(`${base}/api/scans`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: href, deep: true }),
      }).then((r) => r.json());
      if (res.scan_id) window.open(`${base}/scans/${res.scan_id}`, "_blank");
    } catch { window.open(base, "_blank"); }
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
