import { expect, test } from "@playwright/test";

/**
 * Full-stack smoke (v0.14): the suite runs against REAL services - Postgres +
 * API + the production dashboard build - started by CI (see .github/workflows).
 * It exists to prove the automated pipeline works as one system, per the
 * master plan; individual logic is covered by the unit + integration suites.
 *
 * v0.31: the dashboard requires a real reviewer session. CI mints a reviewer
 * and exports E2E_REVIEWER_TOKEN; this suite signs in through the real login
 * form before every authenticated test.
 */

async function signIn(page: import("@playwright/test").Page) {
  const token = process.env.E2E_REVIEWER_TOKEN;
  if (!token) throw new Error("E2E_REVIEWER_TOKEN is required for the dashboard suite");
  await page.goto("/login");
  await page.getByLabel("Personal reviewer token").fill(token);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname !== "/login", { timeout: 15_000 });
}

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("unauthenticated visitors are redirected to the login form", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByLabel("Personal reviewer token")).toBeVisible();
});

test("app shell: brand, primary nav, and a green API health dot", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator(".brand")).toContainText("MTK RADAR");
  for (const label of [
    "Overview",
    "Radar",
    "Review",
    "Queue",
    "Studio",
    "Calendar",
    "Growth",
    "Sources",
    "Connections",
    "Settings",
  ]) {
    await expect(page.locator(".site-nav a", { hasText: label })).toBeVisible();
  }

  // The probe flips red/green/unknown based on the real /health endpoint.
  // With the stack up it must go green within a few seconds.
  await expect(page.locator(".site-header [aria-label='API online']")).toBeVisible({
    timeout: 15_000,
  });
});

test("overview, radar, studio and analytics load real data from the API", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toContainText("Truth-first content radar");

  await page.goto("/radar");
  await expect(page.locator("h1")).toContainText("Trend radar");
  await expect(page.locator("main")).not.toContainText("unreachable");

  await page.goto("/studio");
  await expect(page.locator("h1")).toContainText("Content studio");
  await expect(page.locator("main")).not.toContainText("unreachable");

  await page.goto("/analytics");
  await expect(page.locator("h1")).toContainText("Analytics");
  // the page renders aggregate sections once the API responds
  await expect(page.locator("main")).not.toContainText("unreachable");
});

test("operator console: queue, connections and settings render live data", async ({ page }) => {
  // v0.19: the pages where the operator adds keys, connects accounts and
  // watches the automation — they must work against the real API.
  await page.goto("/queue");
  await expect(page.locator("h1")).toContainText("Queue");
  await expect(page.locator("main")).not.toContainText("unreachable");

  await page.goto("/connections");
  await expect(page.locator("h1")).toContainText("Connections");
  await expect(page.locator("main")).not.toContainText("unreachable");

  await page.goto("/settings");
  await expect(page.locator("h1")).toContainText("Settings");
  await expect(page.locator("main")).not.toContainText("unreachable");
});

test("sources page lists registered sources and the add form", async ({ page }) => {
  // v0.20: without a source there is nothing to collect — registering one
  // must be possible from the desk, not from curl.
  await page.goto("/sources");
  await expect(page.locator("h1")).toContainText("Sources");
  await expect(page.locator("main")).not.toContainText("unreachable");
  await expect(page.locator("#src-provider")).toBeVisible();
  await expect(page.locator("#src-adapter")).toBeVisible();
});

test("source permission can be attested and revoked from the desk", async ({ page }) => {
  // v0.31: machine collection is blocked until a human records the terms
  // reference. This drives the real form instead of only asserting a heading.
  const provider = `E2E Source ${Date.now()}`;
  await page.goto("/sources");
  await page.locator("#src-provider").fill(provider);
  await page.locator("#src-domain").fill("example.com");
  await page.locator("#src-adapter").selectOption("manual");
  await page.locator("#src-tier").selectOption("A_provider_owned");
  await page.getByRole("button", { name: "Register source" }).click();
  await expect(page.getByText(/Source registered|already registered/)).toBeVisible();

  const row = page.locator("tr", { hasText: provider });
  await expect(row).toBeVisible();
  await row.getByLabel(`Terms reference for ${provider}`).fill("https://example.com/terms");
  await row.getByRole("button", { name: "Attest permission" }).click();
  await expect(row.getByText("permission current ✓")).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await row.getByRole("button", { name: "Revoke permission" }).click();
  await expect(row.getByText("not reviewed ⚠")).toBeVisible();
});

test("verified offer workspace exposes evidence, claims and format-gated script generation", async ({ page }) => {
  // v0.31: the P0 operator workflows must be reachable from one verified
  // offer: snapshot provenance, editable claims, and a format chooser that
  // refuses to invent a first-person claim.
  const stamp = Date.now();
  const provider = `E2E Offer ${stamp}`;
  const source = await page.request.post("/api/backend/sources", {
    data: {
      provider,
      canonical_domain: "example.com",
      category: "student_programs",
      adapter: "manual",
      trust_tier: "A_provider_owned",
    },
  });
  expect(source.ok()).toBeTruthy();
  const sourceId = (await source.json()).id;
  const attest = await page.request.post(`/api/backend/sources/${sourceId}/tos-review`, {
    data: { reference: "https://example.com/terms" },
  });
  expect(attest.ok()).toBeTruthy();

  const created = await page.request.post("/api/backend/offers", {
    data: { provider, category: "student_programs", offer_type: "coupon" },
  });
  expect(created.ok()).toBeTruthy();
  const offerId = (await created.json()).id;
  expect((await page.request.post(`/api/backend/offers/${offerId}/transition`, {
    data: { to: "evidence_needed" },
  })).ok()).toBeTruthy();

  const url = `https://example.com/e2e-${stamp}`;
  const text = "Use promo code SAVE2026 for verified students only.";
  const evidence = await page.request.post(`/api/backend/offers/${offerId}/evidence`, {
    data: {
      url,
      source_id: sourceId,
      official: true,
      captured_content: text,
      excerpt: text,
    },
  });
  expect(evidence.ok()).toBeTruthy();
  const evidenceId = (await evidence.json()).id;
  const fields = Object.fromEntries(
    [["promo_code", "SAVE2026"], ["eligibility", "students"]].map(([name, value]) => [
      name,
      {
        value,
        excerpt: text,
        evidence_url: url,
        evidence_id: evidenceId,
        confidence: 0.8,
      },
    ]),
  );
  const extraction = await page.request.post(`/api/backend/offers/${offerId}/extraction`, {
    data: {
      fields,
      coverage: {
        version: "paragraph-groups/1",
        sections_total: 1,
        max_section_chars: 6000,
        evidence_ids: [evidenceId],
      },
    },
  });
  expect(extraction.ok()).toBeTruthy();
  const verified = await page.request.post(`/api/backend/offers/${offerId}/transition`, {
    data: { to: "verified" },
  });
  expect(verified.ok()).toBeTruthy();

  await page.goto(`/offers/${offerId}`);
  await expect(page.locator("h1")).toContainText(provider);
  await expect(page.getByRole("heading", { name: /Evidence \(1\)/ })).toBeVisible();
  await expect(page.getByText("Snapshot & provenance")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Claims & conflicts/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Generate script/ })).toBeVisible();
  await expect(page.locator("label[for^='format-']")).toContainText("Format");
  await page.locator("select[id^='format-']").selectOption("claim_walkthrough");
  await expect(page.getByText(/No reviewer-attested demonstrated claim/)).toBeVisible();

  await page.locator("select[id^='format-']").selectOption("official_explainer");
  await page.getByRole("button", { name: /Generate script/ }).click();
  await expect(page.getByText(/Latest: v1/)).toBeVisible();
  await expect(page.getByText("official_explainer", { exact: true })).toBeVisible();
});

test("start automation and Needs You render the v0.30 operator gates", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".automation-card h2")).toContainText("Start automation");
  await expect(page.locator(".automation-card")).toContainText("workers online");

  await page.goto("/attention");
  await expect(page.locator("h1")).toContainText("Needs You");
  await expect(page.locator("main")).not.toContainText("did not return the attention inbox");
  await expect(page.locator(".attention-kpis")).toBeVisible();
});
