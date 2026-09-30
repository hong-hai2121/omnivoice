import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { chromium, expect } from "@playwright/test";
import { mkdtemp, writeFile, rm, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { importQueue, validateJob, isTikTok, mergeScan, episodeKey } from "../extension/model.js";
import { pageTask } from "../extension/dom.js";

const root = fileURLToPath(new URL("../", import.meta.url));
let context, directory, worker, dashboard, tab, video;
let scannedRows = [];
let scannedSchedule = null;
let scannedInventory = {};
const tomorrow = new Date(Date.now() + 86400_000);
const date = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;
const fixture = `<!doctype html><html><body>
  <input type="file" accept="video/mp4">
  <div contenteditable="true" role="textbox" aria-label="Description" style="width:500px;height:90px;border:1px solid"></div>
  <label><input type="checkbox" checked id="schedule">Schedule</label>
  <input type="date" aria-label="Date"><input type="time" aria-label="Time">
  <button id="publish" onclick="window.published=true">Schedule</button>
  <script>window.toggleCount=0; document.getElementById('schedule').addEventListener('click',()=>window.toggleCount++);</script>
</body></html>`;
const task = (action, data = {}) => tab.evaluate(`(${pageTask.toString()})(${JSON.stringify(action)},${JSON.stringify(data)})`);
const message = request => dashboard.evaluate(request => chrome.runtime.sendMessage(request), request);

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "omnivoice-extension-test-"));
  video = path.join(directory, "fixture.mp4");
  await writeFile(video, Buffer.from("test file bytes, not a real video"));
  const extension = path.join(root, "extension");
  context = await chromium.launchPersistentContext(path.join(directory, "profile"), {
    headless: true, channel: "chromium", args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  const id = new URL(worker.url()).host;
  await context.route("https://www.tiktok.com/**", route => route.fulfill({ contentType: "text/html", body: fixture }));
  await context.route("http://127.0.0.1:8771/**", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({ ok: true, root: "D:\\kich_ban", muc: scannedRows, schedule: scannedSchedule, ghi_chu: [], ...scannedInventory }),
  }));
  tab = await context.newPage(); await tab.goto("https://www.tiktok.com/tiktokstudio/upload");
  dashboard = await context.newPage(); await dashboard.goto(`chrome-extension://${id}/dashboard.html`);
  await dashboard.locator("#tab option").waitFor({ state: "attached" });
});
after(async () => {
  await context?.close();
  if (directory) await rm(directory, { recursive: true, force: true });
});

test("queue import preserves unicode and scheduling, creates unique IDs", () => {
  const rows = importQueue({ muc: [{ id: "old", tieu_de: "Tiếng Việt", video: "D:\\video.mp4", gio_dang: date + "T20:00" }] });
  assert.equal(rows[0].tieu_de, "Tiếng Việt");
  assert.notEqual(rows[0].id, "old");
  validateJob(rows[0], true);
  assert.throws(() => validateJob({ ...rows[0], video: "relative.mp4" }, false));
  assert.throws(() => validateJob({ ...rows[0], gio_dang: "2020-01-01T20:00" }, true));
  assert.throws(() => validateJob({ ...rows[0], gio_dang: date + "T20:03" }, true));
  assert.equal(isTikTok("https://www.tiktok.com.evil.test"), false);
});
test("scan merges by episode, preserves edits and schedules, refreshes generated fields", () => {
  const rows = importQueue([{ video: "D:\\episodes\\A105\\old.mp4", tieu_de: "Edited", gio_dang: date + "T20:00" }]);
  const incoming = importQueue([{ video: "d:/episodes/A105/[Full] new.mp4", tieu_de: "Source", hashtag: "#one" }]);
  assert.equal(mergeScan(rows, incoming).added, 0);
  assert.equal(rows[0].video, incoming[0].video);
  assert.equal(rows[0].tieu_de, "Edited");
  assert.equal(rows[0].gio_dang, date + "T20:00");
  assert.equal(mergeScan(rows, incoming).updated, 0);
  incoming[0].hashtag = "#two";
  mergeScan(rows, incoming);
  assert.equal(rows[0].hashtag, "#two");
  rows[0].hashtag = "#manual";
  incoming[0].hashtag = "#three";
  mergeScan(rows, incoming);
  assert.equal(rows[0].hashtag, "#manual");
  rows[0].trang_thai = "done";
  incoming[0].video = "D:\\episodes\\A105\\short.mp4";
  mergeScan(rows, incoming);
  assert.notEqual(rows[0].video, incoming[0].video);
  assert.equal(mergeScan([], incoming, [episodeKey(incoming[0].video)]).added, 0);
});
test("an already checked schedule control is never toggled off", async () => {
  assert.equal(await task("schedule"), "already");
  assert.equal(await tab.evaluate(() => window.toggleCount), 0);
  await tab.locator("#schedule").uncheck();
  assert.equal(await task("schedule"), "enabled");
  assert.equal(await tab.locator("#schedule").isChecked(), true);
  assert.equal(await tab.evaluate(() => window.published), undefined);
});
test("ambiguous schedule controls fail without clicking publish", async () => {
  await tab.setContent('<label><input type="checkbox">Schedule</label><label><input type="checkbox">Schedule</label><button onclick="window.published=true">Schedule</button>');
  await assert.rejects(() => task("schedule"), /Chua nhan dien/);
  assert.equal(await tab.evaluate(() => window.published), undefined);
  await tab.reload();
});
test("real extension uploads via CDP, fills caption, verifies schedule, leaves other tab active", async () => {
  const tabId = Number(await dashboard.locator("#tab").inputValue());
  const activeBefore = await dashboard.evaluate(async () => (await chrome.tabs.query({ active: true }))[0].id);
  const result = await message({ type: "prepare", tabId, row: { id: "test", video, tieu_de: "Tiếng Việt", hashtag: "#audio #fyp", gio_dang: date + "T20:00" }, schedule: true });
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files[0].name), "fixture.mp4");
  assert.equal(await task("captionCheck", { text: "Tiếng Việt\n#audio #fyp" }), true);
  assert.equal(await task("scheduleCheck", { date, time: "20:00" }), true);
  assert.equal(await tab.evaluate(() => window.published), undefined);
  assert.equal(await dashboard.evaluate(async () => (await chrome.tabs.query({ active: true }))[0].id), activeBefore);
  const progress = await dashboard.evaluate(async () => (await chrome.storage.local.get("progress")).progress);
  assert.equal(progress.status, "review");
  const again = await message({ type: "prepare", tabId, row: { id: "test", video }, schedule: false });
  assert.equal(again.ok, false);
  assert.match(again.error, /Tab dang co video/);
});
test("readonly accessible calendar and time picker are supported", async () => {
  await tab.setContent(`<label><input type="radio" checked>Schedule</label>
    <input readonly aria-label="Date" id="day"><input readonly aria-label="Time" id="time">
    <button aria-label="${date}" onclick="document.querySelector('#day').value='${date}'">${tomorrow.getDate()}</button>
    <div role="listbox" aria-label="Hour"><button role="option" onclick="window.hour='20'">20</button></div>
    <div role="listbox" aria-label="Minute"><button role="option" onclick="document.querySelector('#time').value=window.hour+':00'">00</button></div>`);
  assert.equal(await task("openDate"), true);
  assert.equal(await task("pickDate", { value: date }), "picked");
  assert.equal(await task("pickTime", { part: "hour", value: "20" }), true);
  assert.equal(await task("pickTime", { part: "minute", value: "00" }), true);
  assert.equal(await task("scheduleCheck", { date, time: "20:00" }), true);
  await tab.reload();
});
test("stop interrupts wait and releases debugger", async () => {
  await tab.setContent('<input type="file" accept="video/mp4">');
  const tabId = Number(await dashboard.locator("#tab").inputValue());
  const running = message({ type: "fill", tabId, row: { id: "stop", video, tieu_de: "test" }, schedule: false });
  await expect.poll(() => dashboard.evaluate(async () => (await chrome.storage.local.get("progress")).progress?.status)).toBe("running");
  assert.equal((await message({ type: "inspect", tabId })).ok, false);
  await message({ type: "stop" });
  const result = await running;
  assert.equal(result.ok, false);
  assert.match(result.error, /Da dung/);
  assert.equal((await message({ type: "status" })).running, false);
  await tab.reload();
});
test("dashboard imports existing queue, defaults scheduling and publishing on, renders desktop and mobile", async () => {
  const errors = [];
  dashboard.on("pageerror", error => errors.push(error.message));
  await dashboard.locator("#json-file").setInputFiles(path.resolve(root, "../danh_sach.json"));
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length > 0);
  assert.equal(await dashboard.locator("#schedule").isChecked(), true);
  assert.equal(await dashboard.locator("#publish").isChecked(), true);
  assert.equal((await message({ type: "status" })).running, false);
  await mkdir(path.join(root, "test-results"), { recursive: true });
  for (const [width, height, name] of [[1440, 960, "desktop"], [390, 844, "mobile"]]) {
    await dashboard.setViewportSize({ width, height });
    await dashboard.screenshot({ path: path.join(root, "test-results", name + ".png") });
    assert.equal(await dashboard.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.ok(await dashboard.locator("svg.lucide").count() > 4);
  }
  assert.deepEqual(errors, []);
  await dashboard.setViewportSize({ width: 1440, height: 960 });
});
test("dashboard auto-scans on open and refreshes periodically without duplicates", async () => {
  await dashboard.evaluate(() => chrome.storage.local.clear());
  scannedRows = [{ video: "D:\\episodes\\A200\\[Full] video.mp4", tieu_de: "Full ở Video 200", hashtag: "#MimiAudioSo200" }];
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 1);
  assert.equal(await dashboard.locator('#rows textarea[aria-label="Tiêu đề"]').inputValue(), "Full ở Video 200");
  await dashboard.locator('#rows textarea[aria-label="Tiêu đề"]').fill("Tiêu đề đã sửa");
  await dashboard.locator("#scan").click();
  await dashboard.waitForFunction(() => !document.querySelector("#scan").disabled);
  assert.equal(await dashboard.locator("#rows tr").count(), 1);
  assert.equal(await dashboard.locator('#rows textarea[aria-label="Tiêu đề"]').inputValue(), "Tiêu đề đã sửa");
  await dashboard.clock.install();
  await dashboard.locator("h1").click();
  scannedRows.push({ video: "D:\\episodes\\A201\\[Full] video.mp4", tieu_de: "Video 201" });
  // Reload creates the interval under the controlled clock.
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 2);
  scannedRows.push({ video: "D:\\episodes\\A202\\[Full] video.mp4", tieu_de: "Video 202" });
  await dashboard.clock.fastForward(30_000);
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 3);
  await dashboard.locator("#auto-scan").uncheck();
  scannedRows.push({ video: "D:\\episodes\\A203\\[Full] video.mp4", tieu_de: "Video 203" });
  await dashboard.clock.fastForward(30_000);
  assert.equal(await dashboard.locator("#rows tr").count(), 3);
});
test("dashboard restores JSON and fills following dates, then reflows after a manual change", async () => {
  await dashboard.evaluate(() => chrome.storage.local.clear());
  scannedRows = [124, 125, 126].map(n => ({ video: `D:\\episodes\\A${n}\\[Full] video.mp4`, hashtag: `#MimiAudioSo${n}`, tieu_de: `Video ${n}` }));
  scannedSchedule = { khung_gio: "08:00, 20:00", muc: [{ ...scannedRows[0], gio_dang: date + "T20:00" }] };
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 3);
  const times = dashboard.locator('#rows input[type="datetime-local"]');
  assert.equal(await times.nth(0).inputValue(), date + "T20:00");
  const expected = new Date(date + "T08:00"); expected.setDate(expected.getDate() + 1);
  const nextDay = `${expected.getFullYear()}-${String(expected.getMonth() + 1).padStart(2, "0")}-${String(expected.getDate()).padStart(2, "0")}`;
  assert.equal(await times.nth(1).inputValue(), nextDay + "T08:00");
  assert.equal(await times.nth(2).inputValue(), nextDay + "T20:00");
  await times.nth(1).fill(nextDay + "T20:00");
  await times.nth(1).dispatchEvent("change");
  const later = new Date(expected); later.setDate(later.getDate() + 1);
  const laterDay = `${later.getFullYear()}-${String(later.getMonth() + 1).padStart(2, "0")}-${String(later.getDate()).padStart(2, "0")}`;
  assert.equal(await times.nth(2).inputValue(), laterDay + "T08:00");
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 3);
  assert.equal(await times.nth(1).inputValue(), nextDay + "T20:00");
});
test("JSON status, bulk and individual variants, filtering and select-all work in the dashboard", async () => {
  await dashboard.evaluate(() => chrome.storage.local.clear());
  scannedRows = [124, 125].map(n => ({ video: `D:\\episodes\\A${n}\\[Full] video.mp4`, tieu_de: `Video ${n}`,
    variants: { dai: `D:\\episodes\\A${n}\\[Full] video.mp4`, nua: `D:\\episodes\\A${n}\\Full ở video.mp4`, ngan: `D:\\episodes\\A${n}\\short.mp4` } }));
  scannedSchedule = { khung_gio: "08:00, 20:00", muc: [
    { ...scannedRows[0], trang_thai: "lỗi lịch", ghi_chu: "Kiểm tra ngày", gio_dang: date + "T20:00" },
    { ...scannedRows[1], trang_thai: "chờ" },
  ] };
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 2);
  assert.equal(await dashboard.locator("#rows .status").first().innerText(), "lỗi lịch");
  assert.equal(await dashboard.locator("#rows .status").first().getAttribute("title"), "Kiểm tra ngày");
  await dashboard.locator("#select-all").check();
  assert.equal(await dashboard.locator("#selection-count").innerText(), "2 đã chọn");
  assert.equal(await dashboard.locator("#prepare").isEnabled(), true);
  await dashboard.locator("#publish").uncheck();
  assert.equal(await dashboard.locator("#prepare").isDisabled(), true);
  await dashboard.locator("#variant-half").click();
  await dashboard.waitForFunction(() => document.querySelector("#log").textContent.includes("Đã đổi 2 video"));
  assert.deepEqual(await dashboard.locator(".video-select").evaluateAll(els => els.map(el => el.value)), ["nua", "nua"]);
  await dashboard.locator("#scan").click();
  await dashboard.waitForFunction(() => !document.querySelector("#scan").disabled);
  assert.deepEqual(await dashboard.locator(".video-select").evaluateAll(els => els.map(el => el.value)), ["nua", "nua"]);
  await dashboard.locator(".video-select").first().selectOption("dai");
  await dashboard.waitForFunction(() => document.querySelector("#log").textContent.includes("Đã đổi 1 video sang bản full"));
  assert.deepEqual(await dashboard.locator(".video-select").evaluateAll(els => els.map(el => el.value)), ["dai", "nua"]);
  await dashboard.locator("#status-filter").selectOption("error");
  assert.equal(await dashboard.locator("#rows tr").count(), 1);
  await dashboard.locator("#status-filter").selectOption("all");
  await dashboard.locator("#search").fill("125");
  assert.equal(await dashboard.locator("#rows tr").count(), 1);
  assert.equal(await dashboard.locator("#selection-count").innerText(), "2 đã chọn (1 đang ẩn)");
  await dashboard.locator("#clear-selection").click();
  await dashboard.locator('#rows input[type="checkbox"]').check();
  assert.equal(await dashboard.locator("#prepare").isEnabled(), true);
  assert.match(await dashboard.locator("#action-state").innerText(), /Sẵn sàng: Video 125/);
  await dashboard.locator("#search").fill("");
});
test("selecting one video enables preparation even while a directory scan is pending", async () => {
  await dashboard.evaluate(() => chrome.storage.local.clear());
  scannedRows = [{ video, tieu_de: "Video được chọn", hashtag: "#test" }];
  scannedSchedule = null;
  await tab.reload();
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll("#rows tr").length === 1 && !document.querySelector("#scan").disabled);
  await dashboard.locator("#schedule").uncheck();
  await dashboard.locator("#publish").uncheck();
  await dashboard.locator('#rows input[type="checkbox"]').check();
  assert.equal(await dashboard.locator("#prepare").isEnabled(), true);
  let releaseScan, notifyScan;
  const hold = new Promise(resolve => { releaseScan = resolve; });
  const requested = new Promise(resolve => { notifyScan = resolve; });
  const slowRoute = async route => {
    notifyScan(); await hold;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, muc: scannedRows, root: "test", ghi_chu: [] }) });
  };
  await context.route("http://127.0.0.1:8771/**", slowRoute);
  try {
    await dashboard.locator("#scan").click(); await requested;
    assert.equal(await dashboard.locator("#prepare").isEnabled(), true);
    await dashboard.locator("#prepare").click();
    await dashboard.waitForFunction(() => document.querySelector("#state").textContent === "Chờ kiểm tra");
    assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files[0].name), "fixture.mp4");
    assert.equal(await task("captionCheck", { text: "Video được chọn\n#test" }), true);
  } finally {
    releaseScan();
    await context.unroute("http://127.0.0.1:8771/**", slowRoute);
    // Finish the held scan before the next test replaces its response data and storage.
    await dashboard.waitForFunction(() => !document.querySelector('#scan').disabled);
  }
});

test("a successful scan removes deleted folders and persists the remaining selection", async () => {
  await dashboard.evaluate(() => chrome.storage.local.clear());
  scannedRows = [100, 101].map(n => ({ video: `D:\\kich_ban\\A${n}\\full.mp4`, tieu_de: `Video ${n}` }));
  scannedSchedule = null;
  scannedInventory = { folders_complete: true, folders: ['D:\\kich_ban\\A100', 'D:\\kich_ban\\A101'] };
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll('#rows tr').length === 2 && !document.querySelector('#scan').disabled);
  await dashboard.locator('#select-all').check();
  scannedRows = [];
  scannedInventory.folders = ['D:\\kich_ban\\A101'];
  await dashboard.locator('#scan').click();
  await dashboard.waitForFunction(() => document.querySelectorAll('#rows tr').length === 1 && !document.querySelector('#scan').disabled);
  assert.equal(await dashboard.locator('#selection-count').innerText(), '1 đã chọn');
  assert.equal(await dashboard.locator('#rows textarea[aria-label="Tiêu đề"]').inputValue(), 'Video 101');
  assert.match(await dashboard.locator('#scan-status').innerText(), /bỏ 1 dòng/);
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll('#rows tr').length === 1 && !document.querySelector('#scan').disabled);
  const saved = await dashboard.evaluate(() => chrome.storage.local.get(['rows', 'checkedIds']));
  assert.deepEqual(saved.checkedIds, [saved.rows[0].id]);
  scannedInventory.folders_complete = false;
  scannedInventory.folders = [];
  await dashboard.locator('#scan').click();
  await dashboard.waitForFunction(() => !document.querySelector('#scan').disabled);
  assert.equal(await dashboard.locator('#rows tr').count(), 1);
});
