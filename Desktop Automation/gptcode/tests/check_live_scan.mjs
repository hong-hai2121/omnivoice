// Optional integration check: run chay_quet.py first. No TikTok tab is opened.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const profile = await mkdtemp(path.join(tmpdir(), "gptcode-live-scan-"));
let context;
try {
  const extension = path.join(root, "extension");
  context = await chromium.launchPersistentContext(profile, {
    headless: true, channel: "chromium",
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  const page = await context.newPage();
  await page.goto(`chrome-extension://${new URL(worker.url()).host}/dashboard.html`);
  await page.waitForFunction(() => /video · thêm/.test(document.querySelector("#scan-status").textContent), null, { timeout: 20_000 });
  const state = await page.evaluate(async () => ({
    rows: (await chrome.storage.local.get("rows")).rows,
    status: document.querySelector("#scan-status").textContent,
    schedule: document.querySelector("#schedule-status").textContent,
  }));
  assert.ok(state.rows.length > 0, "Expected at least one local video");
  assert.ok(state.rows.every(row => /^[a-z]:\\/i.test(row.video)));
  const response = await fetch("http://127.0.0.1:8771/api/scan", { headers: { "X-Omni": "gptcode-scanner" } });
  const data = await response.json();
  assert.ok(data.schedule, "Scanner must return the JSON schedule");
  const { episodeKey } = await import("../extension/model.js");
  const scheduled = data.schedule.muc.filter(row => row.gio_dang);
  for (const saved of scheduled) {
    const actual = state.rows.find(row => episodeKey(row.video) === episodeKey(saved.video));
    if (actual) assert.equal(actual.gio_dang, saved.gio_dang);
  }
  for (const saved of data.schedule.muc.filter(row => row.trang_thai)) {
    const actual = state.rows.find(row => episodeKey(row.video) === episodeKey(saved.video));
    if (actual && actual.statusOrigin !== "receipt") assert.equal(actual.trang_thai, saved.trang_thai);
  }
  const variants = state.rows.reduce((counts, row) => {
    for (const kind of Object.keys(row.variants || {})) counts[kind] = (counts[kind] || 0) + 1;
    return counts;
  }, {});
  console.log(JSON.stringify({ videos: state.rows.length, variants, restoredStatuses: state.rows.filter(row => row.statusOrigin === "json").length, restoredDates: state.rows.filter(row => row.gio_dang).length, status: state.status, schedule: state.schedule }));
  for (const [width, height, name] of [[1440, 960, "live-scan"], [390, 844, "live-mobile"]]) {
    await page.setViewportSize({ width, height });
    await page.screenshot({ path: path.join(root, "test-results", name + ".png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  }
} finally {
  await context?.close();
  const expectedPrefix = path.join(tmpdir(), "gptcode-live-scan-");
  if (profile.startsWith(expectedPrefix)) await rm(profile, { recursive: true, force: true });
}
