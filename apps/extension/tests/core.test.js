/**
 * EP-04 extension unit tests — chrome API stubs, no browser required.
 *
 * Run: node --test tests/  (also wired into scripts/verify.sh)
 *
 * Covers the plan's acceptance seams: clicked-LINK target (not the page),
 * offline delivery exactly-once logically, bounded outbox + TTL, distinct
 * statuses (saved/duplicate/auth/rejected/rate-limited/timeout/offline),
 * secret fail-closed, tracking-param stripping without identity break,
 * denylist/restricted targets, API-base validation.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  MAX_SELECTION_CHARS,
  boundSelection,
  classifyError,
  classifyResponse,
  createDelivery,
  createOutbox,
  denylistReason,
  findSecrets,
  isRetryable,
  restrictedReason,
  resolveTarget,
  stripTrackingParams,
  validateApiBase,
} from "../core.js";

// ---- stubs ---------------------------------------------------------------

class MemoryStorage {
  constructor() { this.map = new Map(); }
  async get(keys) {
    const out = {};
    for (const k of Array.isArray(keys) ? keys : [keys]) {
      if (this.map.has(k)) out[k] = this.map.get(k);
      if (typeof keys === "object" && !Array.isArray(keys) && !(k in out)) {
        out[k] = keys[k];
      }
    }
    return out;
  }
  async set(obj) { for (const [k, v] of Object.entries(obj)) this.map.set(k, v); }
  async remove(keys) { for (const k of keys) this.map.delete(k); }
}

/** Scripted fetch: queue of handlers, records every request body. */
function fakeFetch(handlers) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body), headers: init.headers });
    const handler = handlers[calls.length - 1] ?? (() => {
      throw new TypeError("network down");
    });
    return handler({ url, body: JSON.parse(init.body) });
  };
  return { impl, calls };
}

// ---- target resolution (the audit's headline bug) -------------------------

describe("resolveTarget", () => {
  const page = { tab: { url: "https://blog.example.com/post", title: "Blog post" } };

  it("saves the right-clicked LINK, keeping the page only as context", () => {
    const target = resolveTarget({
      ...page,
      info: { linkUrl: "https://paper.example.org/study", selectionText: "12% recall" },
    });
    assert.equal(target.url, "https://paper.example.org/study");
    assert.equal(target.contextType, "link");
    assert.equal(target.pageUrl, "https://blog.example.com/post");
    assert.equal(target.selection, "12% recall");
  });

  it("saves the page with the selected text when no link is involved", () => {
    const target = resolveTarget({
      ...page,
      info: { selectionText: "quoted paragraph" },
    });
    assert.equal(target.url, "https://blog.example.com/post");
    assert.equal(target.contextType, "selection");
    assert.equal(target.selection, "quoted paragraph");
    assert.equal(target.pageUrl, "");
  });

  it("plain page save: url is the page, no selection", () => {
    const target = resolveTarget({ ...page, info: {} });
    assert.equal(target.url, "https://blog.example.com/post");
    assert.equal(target.contextType, "page");
    assert.equal(target.selection, "");
  });
});

// ---- restricted / excluded targets ---------------------------------------

describe("restricted and denylisted targets", () => {
  it("refuses browser-internal pages with a useful reason", () => {
    assert.match(restrictedReason("chrome://settings"), /browser pages/);
    assert.match(restrictedReason("edge://extensions"), /browser pages/);
    assert.match(restrictedReason("https://chromewebstore.google.com/x"), /extension store/);
    assert.match(restrictedReason("ftp://files.example.com"), /scheme/);
    assert.match(restrictedReason(""), /no target/);
  });

  it("allows normal http(s) pages", () => {
    assert.equal(restrictedReason("https://example.com/a"), null);
  });

  it("enforces the built-in private-surface denylist", () => {
    assert.match(denylistReason("https://mail.google.com/inbox"), /mail\.google\.com/);
    assert.equal(denylistReason("https://example.com"), null);
  });

  it("supports user wildcard and exact rules", () => {
    assert.match(denylistReason("https://corp.bank.example/x", ["*.bank.example"]), /bank\.example/);
    assert.match(denylistReason("https://webmail.corp.example/", ["webmail.corp.example"]), /webmail/);
    assert.equal(denylistReason("https://bank.example.corp.co/" , ["*.bank.example"]), null);
  });
});

// ---- privacy --------------------------------------------------------------

describe("privacy: tracking params, secrets, bounds", () => {
  it("strips tracking parameters without breaking canonical identity", () => {
    const stripped = stripTrackingParams(
      "https://example.com/p/42?utm_source=x&fbclid=abc&id=42&utm_content=y#top");
    const u = new URL(stripped);
    assert.equal(u.pathname, "/p/42");
    assert.equal(u.searchParams.get("id"), "42");
    assert.ok(!u.searchParams.get("utm_source"));
    assert.ok(!u.searchParams.get("fbclid"));
    assert.equal(u.hash, "");
  });

  it("detects common secret shapes (fail-closed inputs)", () => {
    const secrets = findSecrets(
      "token ghp_0123456789abcdef0123456789abcdef0123 and AKIAIOSFODNN7EXAMPLE");
    assert.ok(secrets.includes("github_token"));
    assert.ok(secrets.includes("aws_access_key"));
    assert.ok(findSecrets("-----BEGIN RSA PRIVATE KEY-----").includes("private_key"));
    assert.ok(findSecrets("password=hunter2").includes("password_field"));
    assert.deepEqual(findSecrets("nothing sensitive here"), []);
    assert.deepEqual(findSecrets(""), []);
  });

  it("bounds the selection (intake, not page extraction)", () => {
    const long = "a".repeat(MAX_SELECTION_CHARS + 500);
    assert.equal(boundSelection(long).length, MAX_SELECTION_CHARS);
  });
});

// ---- configuration --------------------------------------------------------

describe("validateApiBase", () => {
  it("accepts https and loopback http", () => {
    assert.equal(validateApiBase("https://radar.example.com").ok, true);
    assert.equal(validateApiBase("http://localhost:8000").ok, true);
    assert.equal(validateApiBase("http://127.0.0.1:8000").ok, true);
  });

  it("rejects cleartext non-loopback, credentials, fragments, deep paths", () => {
    assert.match(validateApiBase("http://radar.example.com").error, /https/);
    assert.match(validateApiBase("https://user:pw@radar.example.com").error, /username\/password/);
    assert.match(validateApiBase("https://radar.example.com/#setup").error, /fragment/);
    assert.match(validateApiBase("https://radar.example.com/api/v2").error, /ROOT/);
    assert.match(validateApiBase("not a url").error, /valid URL/);
    assert.match(validateApiBase("").error, /required/);
  });

  it("normalizes trailing slashes out of the base", () => {
    const ok = validateApiBase("https://radar.example.com///");
    assert.equal(ok.base, "https://radar.example.com");
    assert.equal(ok.origin, "https://radar.example.com");
  });
});

// ---- response classification ---------------------------------------------

describe("classifyResponse / errors", () => {
  it("maps every distinct user state", () => {
    assert.equal(classifyResponse(201), "saved");
    assert.equal(classifyResponse(200), "saved");
    assert.equal(classifyResponse(401), "auth_expired");
    assert.equal(classifyResponse(403), "auth_expired");
    assert.equal(classifyResponse(429), "rate_limited");
    assert.equal(classifyResponse(422), "rejected");
    assert.equal(classifyResponse(500), "server_error");
  });

  it("offline/timeout/rate-limited retry; terminal states do not", () => {
    assert.ok(isRetryable("offline"));
    assert.ok(isRetryable("timeout"));
    assert.ok(isRetryable("rate_limited"));
    assert.ok(isRetryable("server_error"));
    assert.ok(!isRetryable("saved"));
    assert.ok(!isRetryable("duplicate"));
    assert.ok(!isRetryable("auth_expired"));
    assert.ok(!isRetryable("rejected"));
    assert.equal(classifyError(Object.assign(new Error("x"), { name: "AbortError" })), "timeout");
    assert.equal(classifyError(new TypeError("fetch failed")), "offline");
  });
});

// ---- the outbox + delivery engine -----------------------------------------

function makeEngine(handlers, { clock = 1_700_000_000_000 } = {}) {
  const storage = new MemoryStorage();
  let tick = clock;
  const outbox = createOutbox(storage, { now: () => tick, uuid: () => 0.5 });
  const { impl, calls } = fakeFetch(handlers);
  const delivery = createDelivery({
    fetchImpl: impl,
    outbox,
    config: () => ({ base: "https://radar.example.com", token: "ext-tok" }),
    now: () => tick,
  });
  return {
    outbox, delivery, calls,
    tick: () => (tick += 1000),
    storage,
    async enqueue(payload) { return outbox.enqueue({ createdAt: tick, ...payload }); },
  };
}

const SAVED = { status: 201, json: async () => ({ id: "srv-1", created: true, duplicate: false, canonical_url: "https://x.example/a" }) };
const DUPLICATE = { status: 201, json: async () => ({ id: "srv-1", created: false, duplicate: true, canonical_url: "https://x.example/a" }) };

describe("delivery engine", () => {
  it("one save → saved, with the client idempotency key as external_item_id", async () => {
    const env = makeEngine([() => SAVED]);
    await env.enqueue({ url: "https://x.example/a", title: "A" });
    const outcomes = await env.delivery.flush();
    assert.equal(outcomes[0].statusKey, "saved");
    assert.equal(env.calls[0].body.external_item_id, outcomeId(await firstId(env)));
    assert.equal(env.calls[0].headers.Authorization, "Bearer ext-tok");
    assert.equal(env.calls[0].url, "https://radar.example.com/items");
    const entries = await env.outbox.list();
    assert.equal(entries[0].status, "saved");
    assert.equal(entries[0].itemId, "srv-1");
  });

  it("OFFLINE survives: stays pending, later retry delivers the SAME key once", async () => {
    const env = makeEngine([() => { throw new TypeError("network down"); }, () => SAVED]);
    await env.enqueue({ url: "https://x.example/a", title: "A" });
    await env.delivery.flush();                 // worker "dies" offline
    assert.equal((await env.outbox.list())[0].status, "pending");
    env.tick();
    await env.delivery.flush();                 // restart, network back
    const entries = await env.outbox.list();
    assert.equal(entries[0].status, "saved");
    assert.ok(await env.storage.get("mtk_outbox"));
    // BOTH attempts carried the SAME external_item_id → the server key
    // (extension source, external id) can never create a second row.
    assert.equal(env.calls.length, 2);
    assert.equal(env.calls[0].body.external_item_id, env.calls[1].body.external_item_id);
  });

  it("duplicate answer marks the entry duplicate, not a second save", async () => {
    const env = makeEngine([() => DUPLICATE]);
    await env.enqueue({ url: "https://x.example/a" });
    const outcomes = await env.delivery.flush();
    assert.equal(outcomes[0].status, 201);
    const entries = await env.outbox.list();
    assert.equal(entries[0].status, "duplicate");
  });

  it("timeout is retryable and distinct from 401/422/429", async () => {
    const abort = () => { const e = new Error("aborted"); e.name = "AbortError"; throw e; };
    const env = makeEngine([abort, () => SAVED]);
    await env.enqueue({ url: "https://x.example/a" });
    assert.equal((await env.delivery.flush())[0].statusKey, "timeout");
    assert.equal((await env.outbox.list())[0].lastError, "timeout");
    env.tick();
    assert.equal((await env.delivery.flush())[0].statusKey, "saved");
  });

  it("429 keeps the entry queued; 401 and 422 are terminal failures", async () => {
    const rate = () => ({ status: 429 });
    const env = makeEngine([rate, rate, () => SAVED]);
    await env.enqueue({ url: "https://x.example/a" });
    assert.equal((await env.delivery.flush())[0].statusKey, "rate_limited");
    assert.equal((await env.outbox.list())[0].status, "pending");
    env.tick();
    assert.equal((await env.delivery.flush())[0].statusKey, "rate_limited");
    env.tick();
    assert.equal((await env.delivery.flush())[0].statusKey, "saved");

    const auth = makeEngine([() => ({ status: 401 })]);
    await auth.enqueue({ url: "https://x.example/b" });
    await auth.delivery.flush();
    assert.equal((await auth.outbox.list())[0].status, "failed");
    assert.equal((await auth.outbox.list())[0].lastError, "auth_expired");

    const reject = makeEngine([() => ({ status: 422 })]);
    await reject.enqueue({ url: "https://x.example/c" });
    await reject.delivery.flush();
    assert.equal((await reject.outbox.list())[0].lastError, "rejected");
  });

  it("gives up after MAX_ATTEMPTS with the attempts counter intact", async () => {
    const handlers = Array.from({ length: 6 }, () => () => { throw new TypeError("x"); });
    const env = makeEngine(handlers);
    await env.enqueue({ url: "https://x.example/a" });
    for (let i = 0; i < 6; i++) { await env.delivery.flush(); env.tick(); }
    const entry = (await env.outbox.list())[0];
    assert.equal(entry.status, "abandoned");
    assert.equal(entry.attempts, 5);
  });

  it("bounded outbox: refuses the 51st unsent entry with a useful action", async () => {
    const env = makeEngine([]);
    for (let i = 0; i < 50; i++) {
      const ok = await env.enqueue({ url: `https://x.example/${i}` });
      assert.equal(ok.error, undefined);
    }
    const full = await env.enqueue({ url: "https://x.example/51" });
    assert.match(full.error, /outbox is full/);
  });

  it("TTL prune drops expired pending entries and delivered entries after 7d", async () => {
    const storage = new MemoryStorage();
    let now = 1_700_000_000_000;
    const outbox = createOutbox(storage, { now: () => now });
    await outbox.enqueue({ url: "https://x.example/old-pending", createdAt: now });
    await outbox.enqueue({ url: "https://x.example/old-saved", createdAt: now });
    await outbox.patch((await outbox.list())[1].id, { status: "saved", savedAt: now });
    // fresh: default createdAt = the (already advanced) clock → stays
    // fresh: enqueued AFTER advancing the clock → inside the TTL
    now += 14 * 86_400_000 + 8 * 86_400_000; // beyond pending TTL AND saved TTL
    await outbox.enqueue({ url: "https://x.example/fresh" });
    assert.equal(await outbox.prune(), 2); // old-pending + old-saved go; fresh stays
    const kept = await outbox.list();
    assert.equal(kept.length, 1);
    assert.equal(kept[0].url, "https://x.example/fresh");
  });

  it("retry(entry) resets attempts and delivers exactly that entry", async () => {
    const env = makeEngine([() => { throw new TypeError("x"); }, () => SAVED]);
    await env.enqueue({ url: "https://x.example/a" });
    await env.delivery.flush();
    assert.equal((await env.outbox.list())[0].status, "pending");
    env.tick();
    const outcome = await env.delivery.retry((await env.outbox.list())[0].id);
    assert.equal(outcome.statusKey, "saved");
  });

  it("pageUrl context and handle ride along in the payload", async () => {
    const env = makeEngine([() => SAVED]);
    await env.enqueue({
      url: "https://paper.example.org/study", title: "Study",
      handle: "kashi", contextType: "link", pageUrl: "https://blog.example.com/x",
      selection: "12% gain", observedAt: "2026-10-24T00:00:00Z",
    });
    await env.delivery.flush();
    const body = env.calls[0].body;
    assert.equal(body.account_handle, "kashi");
    assert.equal(body.extra.context_type, "link");
    assert.equal(body.extra.context_url, "https://blog.example.com/x");
    assert.equal(body.selection, "12% gain");
    assert.equal(body.extra.source_kind, "extension_save");
  });
});

// -- helpers ----------------------------------------------------------------

let idCounter = 0;
async function firstId(env) {
  const entries = await env.outbox.list();
  return entries[0].id;
}
function outcomeId(id) { return id; }
