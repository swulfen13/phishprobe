const DEFAULT_BASE = "https://192.248.159.54.nip.io";
const BADGE = {
  safe: { t: "🟢 Keine Auffälligkeiten", c: "#22c55e" },
  suspicious: { t: "🟡 Verdächtig", c: "#f59e0b" },
  phishing: { t: "🔴 Phishing", c: "#ef4444" },
};

const $ = (id) => document.getElementById(id);

async function getBase() {
  const { apiBase } = await chrome.storage.sync.get("apiBase");
  return (apiBase || DEFAULT_BASE).replace(/\/$/, "");
}

(async () => {
  // Prefill with the active tab's URL and the stored server address.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.url && /^https?:/.test(tab.url)) $("url").value = tab.url;
  const { apiBase } = await chrome.storage.sync.get("apiBase");
  $("apiBase").value = apiBase || DEFAULT_BASE;
})();

$("apiBase").addEventListener("change", (e) => {
  chrome.storage.sync.set({ apiBase: e.target.value.trim() });
});

// Secure mode toggle — the guard content script reads this from storage.
chrome.storage.sync.get("secureMode", ({ secureMode }) => {
  $("secure").checked = !!secureMode;
});
$("secure").addEventListener("change", (e) => {
  chrome.storage.sync.set({ secureMode: e.target.checked });
});

// Page badge toggle (default on).
chrome.storage.sync.get("showBadge", ({ showBadge }) => {
  $("badge").checked = showBadge !== false;
});
$("badge").addEventListener("change", (e) => {
  chrome.storage.sync.set({ showBadge: e.target.checked });
});

$("go").addEventListener("click", run);
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });

async function run() {
  const url = $("url").value.trim();
  if (!url) return;
  const base = await getBase();
  $("go").disabled = true;
  $("result").textContent = "Prüfe …";
  try {
    // Instant quick-check for immediate feedback.
    const q = await fetch(`${base}/api/quick?url=${encodeURIComponent(url)}`).then((r) => r.json());
    const b = BADGE[q.level] || { t: q.level, c: "#64748b" };
    $("result").innerHTML = `Schnell-Check: <span class="badge" style="background:${b.c}">${b.t}</span>`;
    // Start the deep scan and open the live result page.
    const res = await fetch(`${base}/api/scans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, deep: true }),
    }).then((r) => r.json());
    if (res.scan_id) {
      chrome.tabs.create({ url: `${base}/scans/${res.scan_id}` });
      window.close();
    }
  } catch (err) {
    $("result").textContent = "Fehler: Server nicht erreichbar.";
  } finally {
    $("go").disabled = false;
  }
}
