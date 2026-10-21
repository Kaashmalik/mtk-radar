import { defineConfig, devices } from "@playwright/test";

/**
 * Dashboard E2E. CI starts Postgres + API (uvicorn) + dashboard (next start)
 * and points API_URL/NEXT_PUBLIC_API_URL at the real API before running.
 * Locally: `pnpm --dir apps/dashboard exec playwright test` with the same
 * stack up (see docs/runbook.md local path).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
