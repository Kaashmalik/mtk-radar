/**
 * MTK RADAR AI — extension core (EP-04).
 *
 * PURE, chrome-free logic so it runs identically in the MV3 service worker
 * and in Node unit tests (node --test). Everything that touches chrome.*
 * lives in background.js / options.js and injects its dependencies here.
 *
 * Core contract with the API (G05 matrix: the extension credential may only
 * POST /items and GET /whoami):
 *   POST {base}/items  → 201 {id, created, duplicate, canonical_url}
 *   GET  {base}/whoami → 200 {actor, auth}
 *
 * Acceptance (plan EP-04): the clicked LINK is saved rather than the current
 * page; an offline save survives worker restart and is delivered ONCE
 * logically; 401/429/duplicate/timeout/bad-content are distinct tested
 * states.
 */

// ---- constants ------------------------------------------------------------

/** The API caps persisted context at 4000; the extension ships 500 for
 * selections — a save-page INTAKE, not whole-page extraction (plan §EP-04). */
export const MAX_SELECTION_CHARS = 500;
export const MAX_TITLE_CHARS = 600;
export const REQUEST_TIMEOUT_MS = 15_000;
export const OUTBOX_MAX = 50;
export const OUTBOX_TTL_DAYS = 14;
export const MAX_ATTEMPTS = 5;

/** Schemes where save-page intake can never be meaningful or private-safe. */
const RESTRICTED_PREFIXES = (
  "chrome:// edge:// about: chrome-extension:// moz-extension:// view-source:"
).split(" ");

const RESTRICTED_HOSTS = new Set([
  "chromewebstore.google.com",
  "chrome.google.com",
]);

/** Intentional domain exclusions: private-communication surfaces the radar
 * must never suggest saving (webmail, chat DMs, identity/log-in pages).
 * Users may extend this list in options; they may not remove the scheme
 * restrictions above. */
export const DEFAULT_DENYLIST = [
  "accounts.google.com",
  "mail.google.com",
  "outlook.live.com",
  "outlook.office.com",
  "mail.proton.me",
  "web.whatsapp.com",
  "web.telegram.org",
  "discord.com",
  "login.microsoftonline.com",
  "signin.aws.amazon.com",
];

/** Tracking parameters that are safe to strip: canonical identity lives in
 * the path + essential query, and the server canonicalizes further. */
const TRACKING_PARAM_RE =
  /^(utm_[a-z_]+|fbclid|gclid|dclid|mc_[a-z]+|ref_src|ref_url|igshid|si|yclid|twclid|_hsenc|_hsmi|s_cid)$/i;

const SECRET_SIGNATURES = [
  { kind: "jwt", re: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}/ },
  { kind: "aws_access_key", re: /\bAKIA[0-9A-Z]{16}\b/ },
  { kind: "private_key", re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  { kind: "slack_token", re: /\bxox[baprs]-[A-Za-z0-9-]{10,}/ },
  { kind: "github_token", re: /\bgh[pousr]_[A-Za-z0-9]{30,}\b/ },
  { kind: "openai_style_key", re: /\bsk-[A-Za-z0-9_-]{20,}\b/ },
  { kind: "basic_auth_url", re: /https?:\/\/[^\s/:@]+:[^\s/@]+@/ },
  { kind: "password_field", re: /\b(password|passwd|pwd|api[_-]?key|secret)\s*[=:]\s*\S+/i },
];

// ---- target / privacy -----------------------------------------------------

/** What the user asked to save, from a context-menu event + tab.
 * RIGHT-CLICKED LINK wins over the page (the audit's core bug): the page URL
 * travels along as CONTEXT in extra.context_url, never as the saved target. */
export function resolveTarget({ info = {}, tab = {} } = {}) {  const linkUrl = info.linkUrl ? String(info.linkUrl) : "";
  if (linkUrl) {
    return {
      url: linkUrl,
      contextType: "link",
      pageUrl: tab.url ? String(tab.url) : "",
      pageTitle: tab.title ? String(tab.title) : "",
      selection: info.selectionText ? String(info.selectionText) : "",
    };
  }
  return {
    url: tab.url ? String(tab.url) : "",
    contextType: info.selectionText ? "selection" : "page",
    pageUrl: "",
    pageTitle: "",
    selection: info.selectionText ? String(info.selectionText) : "",
  };
}

/** Useful, specific refusal for tabs where saving can never work. */
export function restrictedReason(url) {
  if (!url) return "no target: this tab has no address to save";
  const lower = url.toLowerCase();
  if (RESTRICTED_PREFIXES.some((p) => lower.startsWith(p))) {
    return "browser pages (chrome://, add-ons, settings) cannot be saved";
  }
  try {
    const u = new URL(url);
    if (u.protocol !== "http:" && u.protocol !== "https:") {
      return `unsupported address scheme "${u.protocol}" — only http(s) pages can be saved`;
    }
    if (RESTRICTED_HOSTS.has(u.hostname)) {
      return "the browser extension store cannot be saved";
    }
  } catch {
    return "not a valid http(s) address";
  }
  return null;
}

/** Intentional exclusions + the user's own denylist (hostnames, exact match
 * on host or a leading `*.` wildcard). */
export function denylistReason(url, extraDenylist = []) {
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null; // scheme/shape problems are restrictedReason()'s job
  }
  for (const rule of [...DEFAULT_DENYLIST, ...extraDenylist]) {
    const pattern = String(rule).trim().toLowerCase();
    if (!pattern) continue;
    if (pattern.startsWith("*.")) {
      const suffix = pattern.slice(1); // ".example.com"
      if (host === pattern.slice(2) || host.endsWith(suffix)) {
        return `excluded by denylist rule "${pattern}"`;
      }
    } else if (host === pattern) {
      return `excluded by denylist rule "${pattern}"`;
    }
  }
  return null;
}

/** Strip tracking parameters WITHOUT breaking canonical identity: scheme,
 * host, path and non-tracking query survive untouched. */
export function stripTrackingParams(url) {
  try {
    const u = new URL(url);
    for (const key of [...u.searchParams.keys()]) {
      if (TRACKING_PARAM_RE.test(key)) u.searchParams.delete(key);
    }
    u.hash = ""; // anchors are view state, not identity
    return u.toString();
  } catch {
    return url; // invalid URLs are surfaced by restrictedReason()
  }
}

/** Context URL to attach when the saved target is a link.
 *
 * The page is context, not content: a webmail/chat/sign-in URL is omitted
 * entirely, and the remaining URL is reduced to scheme+host+path (queries and
 * fragments can carry tokens or personal identifiers). Returns "" when the
 * context is not safe to upload.
 */
export function pageContextUrl(raw, extraDenylist = []) {
  if (!raw) return "";
  if (restrictedReason(raw) || denylistReason(raw, extraDenylist)) return "";
  try {
    const u = new URL(raw);
    u.search = "";
    u.hash = "";
    return u.toString();
  } catch {
    return "";
  }
}

/** Which secret kinds appear in the text (fail closed: a positive match
 * BLOCKS the save; the user is told to save without the selected text). */
export function findSecrets(text) {
  if (!text) return [];
  const kinds = [];
  for (const sig of SECRET_SIGNATURES) {
    if (sig.re.test(text)) kinds.push(sig.kind);
  }
  return kinds;
}

export function boundSelection(text) {
  return text ? String(text).slice(0, MAX_SELECTION_CHARS) : "";
}

export function boundTitle(text) {
  return text ? String(text).trim().slice(0, MAX_TITLE_CHARS) : "";
}

// ---- configuration --------------------------------------------------------

/** API base validation (plan EP-04: HTTPS everywhere except loopback dev;
 * no credentials in the URL; no fragments; no accidental deep endpoint
 * paths — the extension appends its own paths). */
export function validateApiBase(raw) {
  const value = String(raw ?? "").trim().replace(/\/+$/, "");
  if (!value) return { ok: false, error: "an API URL is required" };
  let u;
  try {
    u = new URL(value);
  } catch {
    return { ok: false, error: "not a valid URL" };
  }
  if (u.username || u.password) {
    return { ok: false, error: "remove the username/password from the URL" };
  }
  if (u.hash) {
    return { ok: false, error: "remove the #fragment from the URL" };
  }
  const loopback = ["localhost", "127.0.0.1", "[::1]", "::1"]
    .includes(u.hostname.toLowerCase());
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return { ok: false, error: "the API URL must be http(s)" };
  }
  if (u.protocol !== "https:" && !loopback) {
    return { ok: false,
             error: "use https:// for any host other than localhost/127.0.0.1" };
  }
  if (u.pathname && u.pathname !== "/") {
    return { ok: false, error: "use the API ROOT (e.g. https://radar.example.com) — paths are added automatically" };
  }
  return { ok: true, base: value, origin: u.origin, loopback };
}

// ---- options-page settings -------------------------------------------------

/**
 * Build the patch persisted to chrome.storage.local.
 *
 * The options page masks a stored token by clearing the input and setting
 * `data-masked`. In that state the token must be omitted entirely: writing
 * `token: ""` here used to wipe a working credential on an unrelated save.
 */
export function settingsPatch(values, { tokenMasked = false } = {}) {
  const patch = { ...values };
  if (tokenMasked) delete patch.token;
  return patch;
}

/**
 * Token to send to the health probe. A masked field means "use the stored
 * token"; an edited field means "use what the operator typed".
 */
export function probeToken({ tokenMasked, typedToken, storedToken }) {
  return tokenMasked ? (storedToken ?? "") : (typedToken ?? "");
}

// ---- response classification ----------------------------------------------

/** One STATUS KEY per user-visible state (plan: 401/429/duplicate/timeout/
 * bad content must be DISTINGUISHABLE):
 *   saved · duplicate · auth_expired · permission_denied · rejected ·
 *   rate_limited · server_error · offline · timeout
 * offline / timeout / rate_limited stay retryable; the others are terminal. */
export function classifyResponse(status) {
  if (status === 200 || status === 201) return "saved";
  if (status === 401 || status === 403) return "auth_expired";
  if (status === 429) return "rate_limited";
  if (status === 422) return "rejected";
  if (status >= 500) return "server_error";
  return "rejected";
}

export function isRetryable(statusKey) {
  return statusKey === "offline" || statusKey === "timeout" ||
         statusKey === "rate_limited" || statusKey === "server_error";
}

/** Classify a thrown fetch error (network down / host permission refused /
 * abort). Host-permission refusals and DNS failures both throw TypeErrors —
 * the distinction is surfaced at capture time via chrome.permissions. */
export function classifyError(err) {
  if (err && err.name === "AbortError") return "timeout";
  return "offline";
}

// ---- durable outbox -------------------------------------------------------

/** storageArea is chrome.storage.local in production, an in-memory stub in
 * tests. The outbox survives MV3 worker death BY DESIGN (storage.local is
 * persistent). Entries:
 *   { id (client idempotency key = API external_item_id), kind, url, title,
 *     selection, handle, observedAt, createdAt, contextType, pageUrl,
 *     status: pending|saved|duplicate|failed|abandoned,
 *     attempts, lastError, itemId, canonicalUrl, savedAt } */
export function createOutbox(storageArea, {
  max = OUTBOX_MAX, ttlDays = OUTBOX_TTL_DAYS, now = Date.now, uuid = Math.random,
} = {}) {
  const KEY = "mtk_outbox";

  const read = async () => {
    const got = await storageArea.get(KEY);
    return Array.isArray(got[KEY]) ? got[KEY] : [];
  };
  const write = (entries) => storageArea.set({ [KEY]: entries });

  return {
    async list() {
      return read();
    },
    /** Returns the created entry, or {error} when the box is full. */
    async enqueue(payload) {
      const entries = await read();
      if (entries.length >= max) {
        return { error: `outbox is full (${max}) — retry or delete older entries in the options page` };
      }
      const entry = {
        id: newId(uuid),
        status: "pending",
        attempts: 0,
        lastError: null,
        createdAt: now(),
        ...payload,
      };
      entries.push(entry);
      await write(entries);
      return { entry };
    },
    /** Oldest-expired-first prune (bounded by TTL, THEN by count). */
    async prune() {
      const cutoff = now() - ttlDays * 86_400_000;
      const entries = await read();
      const kept = entries.filter(
        (e) => (e.status === "pending" || e.status === "failed" ? e.createdAt > cutoff
                                                               : e.createdAt + 7 * 86_400_000 > cutoff),
      );
      if (kept.length !== entries.length) {
        await write(kept);
        return entries.length - kept.length;
      }
      return 0;
    },
    async patch(entryId, changes) {
      const entries = await read();
      const idx = entries.findIndex((e) => e.id === entryId);
      if (idx === -1) return null;
      entries[idx] = { ...entries[idx], ...changes };
      await write(entries);
      return entries[idx];
    },
    async remove(entryId) {
      const entries = await read();
      await write(entries.filter((e) => e.id !== entryId));
    },
    async clearCompleted() {
      const entries = await read();
      await write(entries.filter((e) => e.status === "pending" || e.status === "failed"));
    },
    async pendingCount() {
      const entries = await read();
      return entries.filter((e) => e.status === "pending" || e.status === "failed").length;
    },
  };
}

function newId(uuid = Math.random) {
  // RFC4122 v4-shaped client idempotency key without crypto dependency:
  // uniqueness over a 50-slot outbox only needs collision-resistant local
  // generation; the server dedupe treats it as external_item_id.
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.floor(uuid() * 2 ** 48).toString(36)}-k`;
}

// ---- delivery engine ------------------------------------------------------

/** fetchImpl(requestUrl, init) is injectable. One logical save = ONE
 * external_item_id (entry.id) forever: a timeout followed by a retry posts
 * the SAME key, and the server's (extension-source, external_item_id) unique
 * key turns the retry into the same row — delivered once, logically. */
export function createDelivery({ fetchImpl, outbox, config,
                                 now = Date.now, onStats = null }) {
  const base = () => config().base.replace(/\/+$/, "");
  const headers = () => {
    const h = { "Content-Type": "application/json" };
    const token = config().token;
    if (token) h.Authorization = `Bearer ${token}`;
    return h;
  };

  async function deliver(entry) {
    const body = JSON.stringify({
      url: entry.url,
      title: entry.title || undefined,
      selection: entry.selection || undefined,
      external_item_id: entry.id,
      account_handle: entry.handle || undefined,
      observed_at: new Date(entry.observedAt ?? entry.createdAt).toISOString(),
      extra: {
        source_kind: "extension_save",
        context_type: entry.contextType || "page",
        context_url: entry.pageUrl || undefined,
      },
    });
    const controller = typeof AbortController !== "undefined"
      ? new AbortController() : null;
    const timer = controller
      ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null;
    try {
      const res = await fetchImpl(`${base()}/items`, {
        method: "POST",
        headers: headers(),
        body,
        signal: controller ? controller.signal : undefined,
      });
      const statusKey = classifyResponse(res.status);
      let data = {};
      try { data = await res.json(); } catch { /* body was never required */ }
      return { status: res.status, statusKey, data };
    } catch (err) {
      return { status: 0, statusKey: classifyError(err), data: {} };
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  /** Flush every retryable entry (oldest first). Returns the outcomes. */
  async function flush() {
    await outbox.prune();
    const entries = await outbox.list();
    const retryable = entries
      .filter((e) => e.status === "pending" || e.status === "failed")
      .sort((a, b) => a.createdAt - b.createdAt);

    const outcomes = [];
    for (const entry of retryable) {
      const result = await deliver(entry);
      if (isRetryable(result.statusKey)) {
        const attempts = entry.attempts + 1;
        await outbox.patch(entry.id, attempts >= MAX_ATTEMPTS
          ? { status: "abandoned", attempts, lastError: result.statusKey }
          : { status: "pending", attempts, lastError: result.statusKey });
      } else if (result.statusKey === "saved") {
        await outbox.patch(entry.id, {
          status: result.data.duplicate ? "duplicate" : "saved",
          itemId: result.data.id ?? null,
          canonicalUrl: result.data.canonical_url ?? null,
          savedAt: now(),
          lastError: null,
        });
      } else { // terminal failure (auth_expired, rejected, …)
        await outbox.patch(entry.id, {
          status: "failed", attempts: entry.attempts + 1, lastError: result.statusKey,
        });
      }
      outcomes.push({ id: entry.id, ...result });
    }
    if (onStats) await onStats(await outbox.pendingCount());
    return outcomes;
  }

  /** UI helpers, one entry at a time. */
  async function retry(entryId) {
    const entry = (await outbox.list()).find((e) => e.id === entryId);
    if (!entry) return { error: "entry not found" };
    await outbox.patch(entryId, { status: "pending", attempts: 0, lastError: null });
    return (await flush()).find((o) => o.id === entryId) ?? { id: entryId };
  }

  return { flush, retry, deliver };
}
