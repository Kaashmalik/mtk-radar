/**
 * MTK RADAR AI — save-page intake extension (Manifest V3, EP-04).
 *
 * A save-page INTAKE tool, nothing more: it never browses, screenshotted or
 * crawled. Identity: the dedicated, revocable intake-only credential
 * (MTK_EXTENSION_TOKEN) — never a personal reviewer token, never a platform
 * OAuth secret. Every saved link lands in the review inbox as a CANDIDATE;
 * the human review desk remains the only path from candidate to offer.
 *
 * Config (options page → chrome.storage.local):
 *   apiBase       — API origin (https except loopback dev), validated
 *   token         — the intake-only extension credential
 *   handle        — optional account/collection handle for the inbox
 *   dashboardBase — optional dashboard origin for "Open saved item"
 *
 * EP-04 additions over v0.2: right-clicked links save the LINK (the page
 * travels as context, not as the target), a durable bounded outbox with a
 * client idempotency key (offline saves survive worker restart and are
 * delivered once logically — same external_item_id on every retry), distinct
 * statuses (saved / duplicate / queued / auth expired / permission denied /
 * rejected / offline / timeout), an alarm-driven retry cadence, secret
 * detection that fails closed, tracking-parameter stripping, intentional
 * domain exclusions, and a health probe (GET /whoami) from the options page.
 * All pure logic lives in core.js (unit-tested under Node).
 */

import {
  MAX_SELECTION_CHARS,
  boundSelection,
  boundTitle,
  classifyError,
  createDelivery,
  createOutbox,
  denylistReason,
  findSecrets,
  pageContextUrl,
  restrictedReason,
  resolveTarget,
  stripTrackingParams,
  validateApiBase,
} from "./core.js";

const CONFIG_DEFAULTS = {
  apiBase: "http://localhost:8000",
  token: "",
  handle: "",
  dashboardBase: "",
  denylistExtra: [],
};

const storage = chrome.storage.local;
const outbox = createOutbox(storage);
const delivery = createDelivery({
  fetchImpl: (...args) => fetch(...args),
  outbox,
  config: () => currentConfig,
  onStats: updateQueuedBadge,
});

let currentConfig = { ...CONFIG_DEFAULTS };

async function loadConfig() {
  currentConfig = { ...CONFIG_DEFAULTS, ...(await storage.get(CONFIG_DEFAULTS)) };
  const check = validateApiBase(currentConfig.apiBase);
  currentConfig.base = check.ok ? currentConfig.apiBase : CONFIG_DEFAULTS.apiBase;
  return currentConfig;
}

// ---- install / alarms ------------------------------------------------------

chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeText({ text: "" });
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "mtk-radar-save",
      title: "Save to MTK RADAR",
      contexts: ["page", "selection", "link"],
    });
    chrome.contextMenus.create({
      id: "mtk-radar-open",
      title: "Open MTK RADAR outbox",
      contexts: ["action"],
    });
  });
  chrome.alarms.create("mtk-outbox", { periodInMinutes: 1 });
  void loadConfig().then(() => flushInBackground());
});

chrome.runtime.onStartup.addListener(() => {
  void loadConfig().then(() => flushInBackground());
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "mtk-outbox") void flushInBackground();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.apiBase || changes.token || changes.handle ||
                           changes.dashboardBase || changes.denylistExtra)) {
    void loadConfig();
  }
});

// ---- entry points ----------------------------------------------------------

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "mtk-radar-save") {
    void saveFromContext(info, tab);
  }
  // "mtk-radar-open" opens the options page's outbox section.
  if (info.menuItemId === "mtk-radar-open") {
    chrome.runtime.openOptionsPage();
  }
});

chrome.action.onClicked.addListener((tab) => void saveFromContext({}, tab));

/** Options page / tests → worker: flush, outbox read, health probe, config
 * checks. Nothing here can read private media or mutate anything upstream —
 * the credential is intake-only by server matrix (G05). */
chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  (async () => {
    if (msg?.type === "mtk-radar:flush") {
      respond({ outcomes: await flushInBackground(), outbox: await outbox.list() });
    } else if (msg?.type === "mtk-radar:retry") {
      respond({ outcome: await delivery.retry(msg.id), outbox: await outbox.list() });
    } else if (msg?.type === "mtk-radar:delete") {
      await outbox.remove(msg.id);
      respond({ ok: true, outbox: await outbox.list() });
    } else if (msg?.type === "mtk-radar:clear-done") {
      await outbox.clearCompleted();
      respond({ ok: true, outbox: await outbox.list() });
    } else if (msg?.type === "mtk-radar:outbox") {
      respond({ outbox: await outbox.list() });
    } else if (msg?.type === "mtk-radar:health") {
      respond(await healthProbe(msg.base, msg.token));
    } else if (msg?.type === "mtk-radar:validate") {
      respond(validateApiBase(msg.base));
    } else {
      respond({ error: "unknown message" });
    }
  })();
  return true; // async respond
});

// ---- capture ---------------------------------------------------------------

async function saveFromContext(info, tab) {
  if (!tab) {
    setFailure("no active tab to save");
    return;
  }
  const cfg = await loadConfig();

  // 1. What are we saving? A right-clicked LINK is the target (not the page).
  const target = resolveTarget({
    info,
    tab: { url: tab.url, title: tab.title },
  });
  if (info.selectionText && info.selectionText.length > MAX_SELECTION_CHARS) {
    // resolveTarget already takes info.selectionText verbatim; bound here.
    target.selection = boundSelection(target.selection);
  }

  // 2. Restricted / excluded targets fail with a USEFUL action, not silence.
  const restricted = restrictedReason(target.url);
  if (restricted) {
    setFailure(restricted);
    return;
  }
  const excluded = denylistReason(target.url, cfg.denylistExtra || []);
  if (excluded) {
    setFailure(excluded);
    return;
  }
  const stripped = stripTrackingParams(target.url);
  if (restrictedReason(stripped)) {
    setFailure("stripped tracking parameters left no savable address");
    return;
  }

  // 3. Privacy preview, fail closed: a detected secret BLOCKS the save.
  const secrets = findSecrets(target.selection || "");
  if (secrets.length) {
    setFailure(`possible secret in your selection (${secrets.join(", ")}) — ` +
               "deselect it and save the page without the selection");
    return;
  }

  // 4. A missing host permission (runtime-granted per API origin) must be a
  // distinct, actionable state — not a generic network error.
  const originAllowed = await hasOriginPermission(cfg.base);
  if (!originAllowed) {
    setFailure("this extension has no permission for the API origin — open " +
               "the options page and re-save your settings to grant it");
    return;
  }

  // 5. Enqueue into the durable outbox + immediate best-effort flush.
  const result = await outbox.enqueue({
    kind: "page",
    url: stripped,
    title: boundTitle(target.contextType === "link"
      ? target.selection || target.pageTitle || target.url
      : tab.title),
    selection: boundSelection(target.selection),
    handle: cfg.handle || "",
    observedAt: new Date().toISOString(),
    createdAt: Date.now(),
    contextType: target.contextType,
    pageUrl: pageContextUrl(target.pageUrl, cfg.denylistExtra || []),
  });
  if (result.error) {
    setFailure(result.error);
    return;
  }
  await updateQueuedBadge(await outbox.pendingCount());
  void flushInBackground();
}

// ---- delivery --------------------------------------------------------------

async function flushInBackground() {
  const outcomes = await delivery.flush();
  await paintOutboxState();
  return outcomes;
}

async function paintOutboxState() {
  const entries = await outbox.list();
  const pending = entries.filter((e) => e.status === "pending" || e.status === "failed").length;
  const failed = entries.filter((e) => e.status === "failed" || e.status === "abandoned").length;
  await updateQueuedBadge(pending);
  if (failed && !pending) {
    setFailure("some saves failed (auth expired or rejected) — open the extension options to review");
  } else if (!pending) {
    chrome.action.setTitle({ title: "Save to MTK RADAR" });
    const last = entries.find((e) => e.status === "saved" || e.status === "duplicate");
    if (last) {
      chrome.action.setTitle({
        title: last.status === "duplicate"
          ? "Already in the review inbox — right-click the toolbar icon → Open MTK RADAR outbox"
          : "Saved to the review inbox — right-click the toolbar icon → Open MTK RADAR outbox",
      });
    }
  }
}

// ---- health probe ----------------------------------------------------------

export async function healthProbe(base, token) {
  const check = validateApiBase(base);
  if (!check.ok) return { ok: false, error: check.error };
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const controller = typeof AbortController !== "undefined"
    ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), 8000) : null;
  try {
    const res = await fetch(`${check.base.replace(/\/+$/, "")}/whoami`, { headers });
    if (res.status === 401 || res.status === 403) {
      return { ok: false, error: "token rejected (401) — paste the dedicated MTK_EXTENSION_TOKEN, not a personal token" };
    }
    if (res.status === 429) {
      return { ok: false, error: "rate limited (429) — try again shortly" };
    }
    if (!res.ok) {
      return { ok: false, error: `API responded ${res.status}` };
    }
    const data = await res.json();
    return { ok: true, actor: data.actor ?? null, auth: data.auth ?? "unknown" };
  } catch (err) {
    const kind = classifyError(err);
    return kind === "timeout"
      ? { ok: false, error: "connection timed out" }
      : { ok: false, error: "could not reach the API — check the URL, the API is up, and the browser has host permission for it" };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function hasOriginPermission(base) {
  const check = validateApiBase(base);
  if (!check.ok) return false;
  if (check.loopback) return true; // granted at install
  if (!chrome.permissions) return true; // manifest without optional grants
  return chrome.permissions.contains({ origins: [`${check.origin}/*`] });
}

// ---- badge -----------------------------------------------------------------

async function updateQueuedBadge(pending) {
  if (pending > 0) {
    chrome.action.setBadgeText({ text: String(pending) });
    chrome.action.setBadgeBackgroundColor({ color: "#bf8700" });
    chrome.action.setTitle({
      title: `${pending} save(s) queued offline — delivered automatically when the API is reachable`,
    });
  } else {
    chrome.action.setBadgeText({ text: "" });
    chrome.action.setTitle({ title: "Save to MTK RADAR" });
  }
}

function setFailure(message) {
  chrome.action.setBadgeText({ text: "!" });
  chrome.action.setBadgeBackgroundColor({ color: "#f85149" });
  chrome.action.setTitle({ title: `Save did NOT complete: ${message}` });
  console.warn(`[mtk-radar] ${message}`);
}
