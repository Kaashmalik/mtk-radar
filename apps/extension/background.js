/**
 * MTK RADAR AI — save-current-page extension (Manifest V3, week 2 / v0.17).
 * Captures URL, title, and selected text; sends it to the configured API.
 *
 * Config (options page → chrome.storage.local):
 *   apiBase — API origin, default http://localhost:8000
 *   token   — bearer credential; REQUIRED when the API has MTK_API_TOKEN set
 *   handle  — optional account/collection handle for the discovery inbox
 *
 * Identity: the extension sends the shared worker token (never a personal one).
 * The review inbox remains the human confirmation gate for saved links.
 */

const DEFAULTS = { apiBase: "http://localhost:8000", token: "", handle: "" };

chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeText({ text: "RADAR" });
  chrome.contextMenus.create({
    id: "mtk-radar-save",
    title: "Save to MTK RADAR",
    contexts: ["page", "selection", "link"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "mtk-radar-save" && tab) void captureAndSend(tab);
});
chrome.action.onClicked.addListener((tab) => void captureAndSend(tab));

async function captureSelection(tabId) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => String(window.getSelection?.() ?? ""),
    });
    return result?.result ?? "";
  } catch {
    return "";
  }
}

async function captureAndSend(tab) {
  const selection = await captureSelection(tab.id);
  const cfg = await chrome.storage.local.get(DEFAULTS);
  const base = (cfg.apiBase || DEFAULTS.apiBase).replace(/\/+$/, "");

  /** Confirmation gate: the dashboard review inbox reviews every saved link
   * before it can become an offer (MV3 service workers have no window.confirm). */
  const headers = { "Content-Type": "application/json" };
  if (cfg.token) headers.Authorization = `Bearer ${cfg.token}`;

  try {
    const res = await fetch(`${base}/items`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        url: tab.url,
        title: tab.title,
        selection,
        account_handle: cfg.handle || undefined,
        observed_at: new Date().toISOString(),
      }),
    });
    setBadge(res.ok);
    if (!res.ok && res.status === 401) setHint("token");
  } catch {
    setBadge(false);
    setHint("connection");
  }
}

function setBadge(ok) {
  chrome.action.setBadgeText({ text: ok ? "✓" : "!" });
  if (ok) chrome.action.setBadgeBackgroundColor({ color: "#2ea043" });
  else chrome.action.setBadgeBackgroundColor({ color: "#f85149" });
}

/** Silent failure is the enemy of awareness — surface auth/config problems. */
function setHint(kind) {
  const title =
    kind === "token"
      ? "Saved failed (401): open the extension options and set your API token"
      : "Save failed: check the API URL in the extension options";
  chrome.action.setTitle({ title });
  console.warn(`[mtk-radar] ${title}`);
}
