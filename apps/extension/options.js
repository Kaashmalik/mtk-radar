/**
 * Options page — EP-04: validated pairing, runtime host grant, masked
 * credential display, explicit revoke/reset, health probe (GET /whoami), and
 * the durable outbox manager (retry once / delete / open saved item).
 */

import { probeToken, settingsPatch, validateApiBase } from "./core.js";

const FIELDS = ["apiBase", "token", "handle", "dashboardBase"];
const DEFAULTS = {
  apiBase: "http://localhost:8000",
  token: "",
  handle: "",
  dashboardBase: "",
  denylistExtra: [],
};

let lastGrantedOrigin = null;

const $ = (id) => document.getElementById(id);
const setStatus = (text, ok) => {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${ok ? "ok" : "err"}`;
};

document.addEventListener("DOMContentLoaded", async () => {
  const cfg = { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
  for (const f of FIELDS) $(f).value = cfg[f] ?? "";
  $("denylist").value = (cfg.denylistExtra ?? []).join("\n");
  lastGrantedOrigin = cfg.lastGrantedOrigin || null;
  maskTokenIfPresent(cfg.token);
  await renderOutbox();
  bind();
});

function maskTokenIfPresent(token) {
  if (!token) return;
  const el = $("token");
  el.dataset.masked = "1";
  el.value = "";
  el.placeholder = `saved (ends …${token.slice(-4)}) — type to replace`;
}

function bind() {
  $("form").addEventListener("submit", (e) => void onSave(e));

  // Typing into a masked token replaces it.
  $("token").addEventListener("input", () => { delete $("token").dataset.masked; });

  $("test-conn").addEventListener("click", async () => {
    setStatus("probing…", true);
    const tokenMasked = Boolean($("token").dataset.masked);
    const stored = tokenMasked ? await chrome.storage.local.get("token") : {};
    const probe = await withWorker({
      type: "mtk-radar:health",
      base: $("apiBase").value.trim() || DEFAULTS.apiBase,
      token: probeToken({
        tokenMasked, typedToken: $("token").value.trim(), storedToken: stored.token,
      }),
    });
    renderProbe(probe);
    if (probe?.ok) setStatus("", true);
  });
  $("revoke").addEventListener("click", () => void onRevoke());
  $("flush").addEventListener("click", async () => {
    await withWorker({ type: "mtk-radar:flush" });
    await renderOutbox();
  });
  $("clear-done").addEventListener("click", async () => {
    await withWorker({ type: "mtk-radar:clear-done" });
    await renderOutbox();
  });
}

async function onSave(event) {
  event.preventDefault();
  const values = {};
  for (const f of FIELDS) values[f] = $(f).value.trim();
  if (!values.apiBase) values.apiBase = DEFAULTS.apiBase;

  const check = validateApiBase(values.apiBase);
  if (!check.ok) {
    setStatus(check.error, false);
    return;
  }
  const dashCheck = values.dashboardBase
    ? validateApiBase(values.dashboardBase) : { ok: true };
  if (!dashCheck.ok) {
    setStatus(`dashboard URL: ${dashCheck.error}`, false);
    return;
  }
  // A masked (untouched) token field must not overwrite the stored token.
  const tokenMasked = Boolean($("token").dataset.masked);
  const patch = settingsPatch(values, { tokenMasked });
  const denylistExtra = $("denylist").value.split("\n")
    .map((s) => s.trim()).filter(Boolean).slice(0, 100);

  // Runtime host grant (S15): ask forgiveness-free, host-scoped permission
  // for the new origin, and retire the previous non-loopback origin.
  const granted = await ensureOriginPermission(check.origin, check.loopback);
  if (!granted) {
    setStatus("you declined the host permission — the extension cannot reach that API origin", false);
    return;
  }
  await chrome.storage.local.set({ ...patch, denylistExtra });
  if (!tokenMasked && values.token) maskTokenIfPresent(values.token);
  setStatus("Saved ✓", true);
  const stored = tokenMasked ? await chrome.storage.local.get("token") : {};
  const probe = await withWorker({
    type: "mtk-radar:health",
    base: values.apiBase,
    token: probeToken({
      tokenMasked, typedToken: values.token, storedToken: stored.token,
    }),
  });
  renderProbe(probe);
}

async function ensureOriginPermission(origin, loopback) {
  if (loopback) {
    await rememberGrantedOrigin(origin);
    return true;
  }
  if (!chrome.permissions) return true;
  const pattern = `${origin}/*`;
  if (await chrome.permissions.contains({ origins: [pattern] })) {
    await rememberGrantedOrigin(origin);
    return true;
  }
  const ok = await chrome.permissions.request({ origins: [pattern] });
  if (ok) await rememberGrantedOrigin(origin);
  return ok;
}

/** Persist the granted origin so a reload can retire the previous host.
 * Session-only state used to leave the old permission behind forever. */
async function rememberGrantedOrigin(origin) {
  if (lastGrantedOrigin && lastGrantedOrigin !== origin && chrome.permissions) {
    await chrome.permissions.remove({ origins: [`${lastGrantedOrigin}/*`] })
      .catch(() => {});
  }
  lastGrantedOrigin = origin;
  await chrome.storage.local.set({ lastGrantedOrigin: origin });
}

async function onRevoke() {
  // Explicit credential revoke/reset: clear every stored secret + config and
  // drop any granted non-loopback hosts (the token itself is invalidated
  // server-side by rotating MTK_EXTENSION_TOKEN).
  const stored = await chrome.storage.local.get(DEFAULTS);
  const check = validateApiBase(stored.apiBase ?? "");
  if (!check.loopback && chrome.permissions) {
    await chrome.permissions.remove({ origins: [`${check.origin}/*`] }).catch(() => {});
  }
  await chrome.storage.local.remove(["token", "handle", "apiBase", "dashboardBase", "denylistExtra", "lastGrantedOrigin"]);
  lastGrantedOrigin = null;
  for (const f of FIELDS) $(f).value = "";
  $("denylist").value = "";
  $("token").placeholder = "paste MTK_EXTENSION_TOKEN";
  $("whoami-result").textContent = "";
  await chrome.runtime.sendMessage({ type: "mtk-radar:flush" }).catch(() => {});
  setStatus("Reset — credential cleared from this browser", true);
}

function renderProbe(probe) {
  const el = $("whoami-result");
  if (!probe) { el.textContent = ""; return; }
  if (probe.ok) {
    el.textContent = `Connection OK — authenticated as ${probe.actor ?? "the extension intake credential"} (class: ${probe.auth}).`;
    el.className = "hint ok";
  } else {
    el.textContent = `Probe failed: ${probe.error}`;
    el.className = "hint err";
  }
}

// ---- outbox rendering -------------------------------------------------------

async function withWorker(message) {
  try {
    return await chrome.runtime.sendMessage(message);
  } catch {
    // The worker may be asleep — waking it handles the retry path.
    return null;
  }
}

async function renderOutbox() {
  const res = await withWorker({ type: "mtk-radar:outbox" });
  const entries = res?.outbox ?? [];
  const body = $("outbox-rows");
  if (!entries.length) {
    body.innerHTML = '<tr><td colspan="4" class="hint">Nothing saved yet.</td></tr>';
    return;
  }
  body.innerHTML = "";
  for (const entry of [...entries].reverse()) {
    const tr = document.createElement("tr");
    const label = {
      saved: "saved", duplicate: "duplicate (already in inbox)",
      pending: entry.lastError === "offline" ? "queued offline"
        : entry.lastError === "timeout" ? "queued (timed out once)"
        : entry.lastError === "rate_limited" ? "queued (rate limited)"
        : "queued", failed: `failed (${entry.lastError})`,
      abandoned: `gave up after ${entry.attempts} attempts (${entry.lastError})`,
    }[entry.status] ?? entry.status;
    tr.innerHTML =
      `<td class="st-${entry.status}">${label}</td>` +
      `<td>${escapeHtml(entry.title || entry.url)}<br>
         <span class="hint">${escapeHtml(entry.url)}</span></td>` +
      `<td>${entry.attempts ?? 0}</td>` +
      `<td class="actions"></td>`;
    const actions = tr.querySelector(".actions");
    if (entry.status === "pending" || entry.status === "failed") {
      const retry = document.createElement("button");
      retry.textContent = "Retry now";
      retry.addEventListener("click", () => void retryEntry(entry.id));
      actions.appendChild(retry);
    }
    if (entry.status === "saved" || entry.status === "duplicate") {
      const open = document.createElement("button");
      open.textContent = "Open saved item";
      open.addEventListener("click", () => void openSavedItem(entry));
      actions.appendChild(open);
    }
    const del = document.createElement("button");
    del.textContent = "Delete";
    del.addEventListener("click", () => void removeEntry(entry.id));
    actions.appendChild(del);
    body.appendChild(tr);
  }
}

async function retryEntry(id) {
  await withWorker({ type: "mtk-radar:retry", id });
  await renderOutbox();
}

async function removeEntry(id) {
  await withWorker({ type: "mtk-radar:delete", id });
  await renderOutbox();
}

/** "Open saved item" uses ONLY the id the API returned — the extension never
 * constructs gallery/media URLs or reads anything back. */
async function openSavedItem(entry) {
  if (!entry.itemId) return;
  const cfg = await chrome.storage.local.get(DEFAULTS);
  const dash = (cfg.dashboardBase || "").trim().replace(/\/+$/, "");
  if (!dash) {
    setStatus("set the Dashboard URL to open saved items", false);
    return;
  }
  await chrome.tabs.create({ url: `${dash}/inbox?saved_item=${encodeURIComponent(entry.itemId)}` });
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
