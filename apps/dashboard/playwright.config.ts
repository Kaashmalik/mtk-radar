import { defineConfig, devices } from "@playwright/test";

/**
 * Dashboard E2E. CI starts Postgres + API (uvicorn) + dashboard (next start),
 * sets API_URL/MTK_API_TOKEN/MTK_SESSION_SECRET, mints a reviewer and exports
 * E2E_REVIEWER_TOKEN. Locally: run scripts/verify.sh (or start the same stack
 * and set those variables) before `pnpm --dir apps/dashboard exec playwright test`.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    // CI installs Playwright's bundled Chromium. On a workstation that cannot
    // download it, E2E_CHANNEL=chrome|msedge runs the same suite in a local
    // browser without changing assertions.
    channel: (process.env.E2E_CHANNEL as "chrome" | "msedge" | undefined) || undefined,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
