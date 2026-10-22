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

test("start automation and Needs You render the v0.30 operator gates", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".automation-card h2")).toContainText("Start automation");
  await expect(page.locator(".automation-card")).toContainText("workers online");

  await page.goto("/attention");
  await expect(page.locator("h1")).toContainText("Needs You");
  await expect(page.locator("main")).not.toContainText("did not return the attention inbox");
  await expect(page.locator(".attention-kpis")).toBeVisible();
});
