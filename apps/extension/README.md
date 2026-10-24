# MTK RADAR AI — Save Page extension (browser intake)

A Manifest V3 **save-page intake** tool for the MTK RADAR review desk. It
saves the page you are viewing — or, more importantly, the **right-clicked
link** — as a *candidate* in the discovery inbox. It never publishes, never
crawls, never screenshots, and never holds platform OAuth secrets.

## What gets saved

| You do | What lands in the inbox |
|---|---|
| Click the toolbar icon | The current page's URL + title |
| Select text, then click the toolbar icon | The page + the selected text (capped at 500 chars) |
| Right-click a **link** → "Save to MTK RADAR" | **The link target** (not the page you are on); the page URL rides along as context |
| Right-click the selected text | The page + the selection |

Every save carries a client idempotency key. The server turns that into the
same inbox row on retries — a save is delivered **once, logically**, even if
the worker restarts mid-flight. Every saved link is still just a *candidate*:
a human reviewer must promote it before anything else happens.

## Install (testers — no build step needed)

1. Get two things from your deployment operator:
   the **API URL** (e.g. `https://radar.example.com`) and the dedicated
   **extension intake token** (`MTK_EXTENSION_TOKEN`). This credential can
   only save candidates and probe its own identity — it cannot read private
   media, run jobs, or delete anything. Rotating `MTK_EXTENSION_TOKEN` on the
   server revokes this browser's access immediately.
2. Open `chrome://extensions` (or `edge://extensions`), enable **Developer
   mode**, click **Load unpacked**, and select this `apps/extension/`
   folder.
3. Open the extension's **Options** page:
   - paste the API URL — `https://` is required for any host other than
     `localhost`/`127.0.0.1`; the browser will ask to grant the extension
     access to exactly that origin (you can revoke it any time via
     "Revoke & reset" or the browser's site-permission settings);
   - paste the intake token (stored masked; retype it to replace it);
   - optionally set the **Dashboard URL** to enable the "Open saved item"
     action, and add extra excluded domains (one per line).
4. Press **Test connection settings** — the options page probes
   `GET /whoami` and shows which identity the API sees.

> Loopback development: `http://localhost:8000` works out of the box (that
> origin is granted at install time); no cleartext host outside loopback is
> ever allowed.

## Outbox (offline-first)

- Saves are queued durably (max **50** entries, kept **14 days**) and
  delivered automatically (worker alarm, ~1 minute cadence) or manually via
  **Deliver queued now** on the options page.
- Toolbar badge shows the number of queued saves; each entry shows its state:
  `saved` / `duplicate (already in inbox)` / `queued offline` /
  `queued (timed out once)` / `queued (rate limited)` / `failed (auth
  expired)` / `failed (rejected)` / `gave up after N attempts`.
- Failed auth/rejected entries are terminal and need a human ("Retry now"
  re-sends with the same idempotency key — the server still dedupes).
- "Open saved item" uses **only** the item id the API returned — the
  extension never reads anything back from the API.

## Privacy behaviour (intentional, fail-closed)

- **Secrets block the save**: if the selection looks like a credential
  (JWT, AWS key, GitHub/Slack token, `password=…`, private key block, …) the
  save is refused and you are told to drop the selection.
- **Tracking parameters are stripped** (`utm_*`, `fbclid`, `gclid`, … and
  URL fragments) before upload; the path and non-tracking query are kept, so
  canonical identity is unaffected (the server canonicalizes further).
- **Private surfaces are excluded by default** (webmail, chat DMs,
  sign-in pages — see `DEFAULT_DENYLIST` in `core.js`); extend the list in
  options. Browser-internal pages (`chrome://`, `edge://`, the extension
  store) can never be saved.
- Nothing is uploaded automatically: every save is an explicit click.

## Development

- `core.js` holds ALL pure logic (targets, privacy, outbox, delivery) and is
  unit-tested in Node with Chrome-API stubs:
  `cd apps/extension && node --test tests/` (also wired into
  `scripts/verify.sh`).
- `background.js` (MV3 service worker) and `options.js` are thin chrome
  wiring around `core.js`.
- API contract (see the G05 matrix in `services/api/api_hardening.py`): the
  extension credential may only `POST /items` and `GET /whoami`; the
  server-side idempotency contract is integration-tested in
  `services/api/tests/test_integration.py::test_extension_intake_contract_idempotent_with_context`.

### Not yet proven (honest ledger)

- A **loaded-extension E2E run** (persistent-context Chromium driving a real
  API) — the unit suite stubs `chrome.*`; a Playwright edge-context smoke
  test plus a manual Chrome/Edge smoke on a real profile are still open
  follow-ups. Step-by-step manual smoke: install as above, save a page
  offline (disconnect), observe the queued badge, reconnect, watch it deliver
  exactly once.
- No Firefox claim: this ships Chrome MV3 only.
