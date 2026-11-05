// PhishProbe MV3 service worker.
// Right-click a link -> "Mit PhishProbe prüfen": runs the fast quick-check for
// an instant badge, then starts a full deep scan and opens the live scan page.

const DEFAULT_BASE = "https://192.248.159.54.nip.io";

async function getBase() {
  const { apiBase } = await chrome.storage.sync.get("apiBase");
  return (apiBase || DEFAULT_BASE).replace(/\/$/, "");
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "phishprobe-check",
    title: "Mit PhishProbe prüfen",
    contexts: ["link", "selection", "page"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  const target = info.linkUrl || info.selectionText || info.pageUrl;
  if (target) await check(target);
});

const BADGE_COLORS = { safe: "#22c55e", suspicious: "#f59e0b", phishing: "#ef4444" };
const BADGE_TEXT = { safe: "OK", suspicious: "?", phishing: "!" };

async function check(url) {
  const base = await getBase();
  // 1) Instant quick-check -> badge.
  try {
    const q = await fetch(`${base}/api/quick?url=${encodeURIComponent(url)}`).then((r) => r.json());
    await chrome.action.setBadgeText({ text: BADGE_TEXT[q.level] || "?" });
    await chrome.action.setBadgeBackgroundColor({ color: BADGE_COLORS[q.level] || "#64748b" });
  } catch {
    await chrome.action.setBadgeText({ text: "…" });
  }
  // 2) Start the full deep scan and open the live scan page.
  try {
    const res = await fetch(`${base}/api/scans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, deep: true }),
    }).then((r) => r.json());
    if (res.scan_id) chrome.tabs.create({ url: `${base}/scans/${res.scan_id}` });
  } catch (e) {
    // Fall back to opening the app so the user can paste the link manually.
    chrome.tabs.create({ url: base });
  }
}

// Allow the popup to trigger a check.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "check" && msg.url) {
    check(msg.url).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
});
