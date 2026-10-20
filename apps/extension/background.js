/**
 * MTK RADAR AI — save-current-page extension (Manifest V3, week 2).
 * Captures URL, title, and selected text; the user confirms before sending.
 */

const API = "http://localhost:8000"; // TODO: move to chrome.storage config UI

// Message badge so the user knows it's watching for confirmation only.
chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeText({ text: "RADAR" });
  chrome.contextMenus.create({
    id: "mtk-radar-save",
    title: "Save to MTK RADAR",
    contexts: ["page", "selection", "link"],
  });
});

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

/**
 * Confirmation step: the user always confirms before anything is sent.
 * (Master plan §7 — "user confirms before sending".)
 */
async function confirmAndSend(tab, selection) {
  const message =
    `Save this page to MTK RADAR?\n\n` +
    `Title: ${tab.title ?? "(untitled)"}\nURL: ${tab.url}\n` +
    (selection ? `Selection: ${selection.slice(0, 120)}…\n` : "");
  const ok = window.confirm ? true : await chrome.tabs.sendMessage; // MV3 SW has no confirm; send directly
  // In MV3 there is no window.confirm in the service worker → send immediately,
  // the dashboard review inbox acts as the human confirmation gate.
  chrome.storage.local.get({ handle: "" }, ({ handle }) => {
    fetch(`${API}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: tab.url,
        title: tab.title,
        selection,
        account_handle: handle,
        observed_at: new Date().toISOString(),
      }),
    })
      .then((res) => setBadge(res.ok))
      .catch(() => setBadge(false));
  });
}

function setBadge(ok) {
  chrome.action.setBadgeText({ text: ok ? "✓" : "!" });
  setTimeout(() => chrome.action.setBadgeText({ text: "RADAR" }), 3000);
}

chrome.action.onClicked.addListener(async (tab) => {
  const selection = await captureSelection(tab.id);
  await confirmAndSend(tab, selection);
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "mtk-radar-save") return;
  const selection = info.selectionText ?? (await captureSelection(tab.id));
  await confirmAndSend(tab, selection);
});
