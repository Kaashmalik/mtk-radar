import { expect, test } from "@playwright/test";

/**
 * Full-stack smoke (v0.14): the suite runs against REAL services — Postgres +
 * API + the production dashboard build — started by CI (see .github/workflows).
 * It exists to prove the automated pipeline works as one system, per the
 * master plan; individual logic is covered by the unit + integration suites.
 */

test("app shell: brand, primary nav, and a green API health dot", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator(".brand")).toContainText("MTK RADAR");
  for (const label of [
    "Inbox",
    "Review desk",
    "Queue",
    "Sources",
    "Calendar",
    "Analytics",
    "Connections",
    "Settings",
  ]) {
    await expect(page.locator(".site-nav a", { hasText: label })).toBeVisible();
  }

  // The probe flips red/green/unknown based on the real /health endpoint.
  // With the stack up it must go green within a few seconds.
  await expect(page.locator(".site-header [role=status]")).toHaveAttribute(
    "aria-label",
    "API online",
    { timeout: 15_000 },
  );
});

test("inbox and analytics load real data from the API", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toContainText("MTK RADAR AI");

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
