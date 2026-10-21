/** Options page — persists extension config to chrome.storage.local. */

const FIELDS = ["apiBase", "token", "handle"];
const DEFAULTS = { apiBase: "http://localhost:8000", token: "", handle: "" };

document.addEventListener("DOMContentLoaded", async () => {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  for (const f of FIELDS) document.getElementById(f).value = cfg[f] ?? "";

  document.getElementById("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const values = {};
    for (const f of FIELDS) values[f] = document.getElementById(f).value.trim();
    if (!values.apiBase) values.apiBase = DEFAULTS.apiBase;
    await chrome.storage.local.set(values);
    const status = document.getElementById("status");
    status.textContent = "Saved ✓";
    setTimeout(() => (status.textContent = ""), 2000);
  });
});
