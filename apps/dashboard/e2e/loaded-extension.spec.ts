import { expect, test, chromium } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/**
 * Loaded-extension smoke (EP-04): proves the unpacked Manifest V3 extension
 * works in a REAL Chromium profile against a REAL API - not only the Node
 * unit tests for core.js.
 *
 * verify.sh sets E2E_EXTENSION_DIR, E2E_API_BASE_URL, E2E_EXTENSION_TOKEN and
 * E2E_API_TOKEN; without them the test is skipped so the normal dashboard
 * suite stays self-contained. Extensions cannot be side-loaded in Chromium's
 * old headless shell, so this runs headed (Linux CI needs xvfb-run).
 *
 * The test seeds the same durable-outbox shape the capture path creates,
 * uses the options page's real "Deliver queued now" button, and then reads
 * the inbox through the API: delivery + idempotent duplicate handling are
 * exercised end to end.
 */

const extensionDir = process.env.E2E_EXTENSION_DIR;
const apiBase = process.env.E2E_API_BASE_URL;
const extensionToken = process.env.E2E_EXTENSION_TOKEN;
const apiToken = process.env.E2E_API_TOKEN;

// The spec is typechecked by the dashboard's Node tsconfig, which does not
// depend on @types/chrome. Only the one storage call made inside the extension
// page needs a declaration.
declare const chrome: {
  storage: {
    local: {
      set(items: Record<string, unknown>): Promise<void>;
    };
  };
};

test("loaded extension pairs, probes the API, and delivers its outbox", async ({
  request,
}, testInfo) => {
  test.skip(
    !extensionDir || !apiBase || !extensionToken || !apiToken,
    "set E2E_EXTENSION_DIR/E2E_API_BASE_URL/E2E_EXTENSION_TOKEN/E2E_API_TOKEN to run the loaded-extension smoke",
  );
  if (!extensionDir || !apiBase || !extensionToken || !apiToken) return;
  test.setTimeout(90_000);

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "mtk-ext-e2e-"));
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    chromiumSandbox: false,
    args: [
      `--disable-extensions-except=${extensionDir}`,
      `--load-extension=${extensionDir}`,
    ],
  });

  try {
    let [worker] = context.serviceWorkers();
    if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 20_000 });
    const extensionId = new URL(worker.url()).host;

    const optionsPage = await context.newPage();
    await optionsPage.goto(`chrome-extension://${extensionId}/options.html`);
    await optionsPage.locator("#apiBase").fill(apiBase);
    await optionsPage.locator("#token").fill(extensionToken);
    await optionsPage.locator("#handle").fill("e2e-extension");
    await optionsPage.getByRole("button", { name: "Save settings" }).click();

    const probe = optionsPage.locator("#whoami-result");
    await expect(probe).toContainText("Connection OK", { timeout: 20_000 });
    await expect(probe).toContainText("class: extension");

    const stamp = Date.now();
    const title = `Loaded extension E2E ${stamp}`;
    const url = `https://example.com/loaded-extension/${stamp}`;
    const pageUrl = `https://blog.example.com/loaded-extension/${stamp}`;

    const entry = (id: string) => ({
      id,
      status: "pending",
      attempts: 0,
      lastError: null,
      createdAt: Date.now(),
      kind: "page",
      url,
      title,
      selection: "Loaded-extension end-to-end delivery.",
      handle: "e2e-extension",
      observedAt: Date.now(),
      contextType: "page",
      pageUrl,
    });

    const deliver = async (entryId: string, expectedStatus: string) => {
      await optionsPage.evaluate(async (queued) => {
        await chrome.storage.local.set({ mtk_outbox: [queued] });
      }, entry(entryId));
      await optionsPage.getByRole("button", { name: "Deliver queued now" }).click();
      const row = optionsPage.locator("#outbox-rows tr", { hasText: title });
      await expect(row.locator(`td.st-${expectedStatus}`)).toBeVisible({
        timeout: 20_000,
      });
    };

    await deliver(`ext-e2e-${stamp}-1`, "saved");
    const first = await request.get(`${apiBase}/items`, {
      params: { q: title, limit: 50 },
      headers: { Authorization: `Bearer ${apiToken}` },
    });
    expect(first.ok()).toBeTruthy();
    const firstItems = (await first.json()) as Array<{ url: string; id: string }>;
    expect(firstItems.filter((item) => item.url === url)).toHaveLength(1);

    // A retry with a different client key but the same URL/title must dedupe
    // through the server's canonical-url + text-hash key (migration 031).
    await deliver(`ext-e2e-${stamp}-2`, "duplicate");
    const second = await request.get(`${apiBase}/items`, {
      params: { q: title, limit: 50 },
      headers: { Authorization: `Bearer ${apiToken}` },
    });
    expect(second.ok()).toBeTruthy();
    const secondItems = (await second.json()) as Array<{ url: string; id: string }>;
    expect(secondItems.filter((item) => item.url === url)).toHaveLength(1);
    expect(secondItems.find((item) => item.url === url)?.id).toBe(firstItems.find(
      (item) => item.url === url,
    )?.id);

    const evidence = {
      schema: "mtk-loaded-extension-e2e/1",
      extension_id: extensionId,
      api_base: apiBase,
      probe: await probe.textContent(),
      item_id: firstItems.find((item) => item.url === url)?.id,
      duplicate_without_second_row: true,
      checked_at: new Date().toISOString(),
    };
    fs.writeFileSync(
      testInfo.outputPath("loaded-extension-evidence.json"),
      JSON.stringify(evidence, null, 2),
    );
  } finally {
    await context.close().catch(() => {});
    fs.rmSync(userDataDir, { recursive: true, force: true });
  }
});
