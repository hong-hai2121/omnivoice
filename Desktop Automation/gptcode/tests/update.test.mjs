import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyPostList, postDate, postAnchors } from '../extension/posts.js';
import { importQueue, mergeScan, pruneMissingFolders, rowKey, NO_VIDEO } from '../extension/model.js';
import { syncSchedule } from '../extension/schedule.js';
import { isolatedExtension } from './helpers.mjs';

const pad = value => String(value).padStart(2, '0');
const day = offset => { const d = new Date(); d.setDate(d.getDate() + offset); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const shown = (iso, hour) => `${Number(iso.slice(8, 10))} tháng ${Number(iso.slice(5, 7))}, ${hour}`;
const title = n => `Full ở Mimi audio Số ${n} | Tiêu đề tập ${n}`;
const post = (n, extra = {}) => ({ id: String(7000 + n), url: `https://www.tiktok.com/@mimi/video/${7000 + n}`,
  caption: `${title(n)} #MimiAudioSo${n} #truyenaudio`, stage: '', icons: [], ...extra });
const row = (n, extra = {}) => ({ id: String(n), video: `D:\\kb\\A${n}\\[Full] v.mp4`, thu_muc: `D:\\kb\\A${n}`,
  tieu_de: title(n), hashtag: `#MimiAudioSo${n}`, gio_dang: '', trang_thai: 'cho', ...extra });

test('TikTok list decides scheduled, published, waiting, review and leaves unread old episodes alone', () => {
  const now = new Date('2026-10-02T17:00');
  const rows = [row(120, { trang_thai: 'đã hẹn giờ', statusOrigin: 'json' }), row(124), row(123), row(125, { trang_thai: 'error', statusOrigin: 'local' }),
    row(126, { video: '', trang_thai: NO_VIDEO }), row(122), row(121, { tieu_de: 'Full ở Mimi audio Số 121 | Tên khác' }), row(127, { trang_thai: 'running' })];
  const list = { complete: false, readAt: '2026-10-02T10:00:00.000Z', posts: [
    post(124, { stage: '3 tháng 10, 8:00 CH', icons: ['Alarm'] }), post(124, { id: '1', stage: '3 tháng 10, 8:00 CH', icons: ['Alarm'] }),
    post(123, { stage: '2 tháng 10, 8:00 SA' }), post(122, { stage: 'Đang xử lý' }), post(121, { stage: '1 tháng 10, 8:00 CH' }),
  ] };
  const result = applyPostList(rows, list, now);
  const byId = Object.fromEntries(rows.map(item => [item.id, item]));
  assert.equal(byId[124].trang_thai, 'đã lên lịch');
  assert.equal(byId[124].gio_dang, '2026-10-03T20:00');
  assert.equal(byId[124].scheduleKind, 'tiktok');
  assert.equal(byId[124].statusOrigin, 'tiktok');
  assert.match(byId[124].ghi_chu, /2 bài trùng tiêu đề/);
  assert.equal(byId[123].trang_thai, 'đã đăng');
  assert.equal(byId[123].gio_dang, '2026-10-02T08:00');
  assert.equal(byId[125].trang_thai, 'cho');
  assert.match(byId[125].ghi_chu, /Chưa thấy trên TikTok/);
  assert.equal(byId[126].trang_thai, NO_VIDEO);
  assert.equal(byId[122].trang_thai, 'review');
  assert.equal(byId[121].trang_thai, 'review');
  assert.match(byId[121].ghi_chu, /Số 121 nhưng tiêu đề khác/);
  assert.equal(byId[120].trang_thai, 'đã hẹn giờ', 'older than every post read: not judged');
  assert.equal(byId[127].trang_thai, 'running');
  assert.deepEqual([result.scheduled, result.published, result.waiting, result.review, result.unknown], [1, 1, 2, 2, 1]);
  assert.deepEqual(applyPostList(rows, list, now).changedIds, []);
  const plain = [row(119)];
  applyPostList(plain, { posts: [post(119, { stage: '' })] }, now);
  assert.equal(plain[0].trang_thai, 'đã đăng', 'a listed post without a date label exists on TikTok');
  const future = [row(118)];
  applyPostList(future, { posts: [post(118, { stage: '4 tháng 10, 8:00 SA' })] }, now);
  assert.equal(future[0].trang_thai, 'đã lên lịch', 'a future date means scheduled even without the alarm icon');
  assert.equal(future[0].gio_dang, '2026-10-04T08:00');
  // A complete list proves absence for old episodes too; a vanished post releases its TikTok time.
  applyPostList(rows, { ...list, complete: true, posts: list.posts.slice(2) }, now);
  assert.equal(byId[120].trang_thai, 'cho');
  assert.equal(byId[124].trang_thai, 'cho');
  assert.equal(byId[124].scheduleKind, 'auto');
  assert.equal(applyPostList(rows, null).changedIds.length, 0);
});

test('dates without a year resolve to the nearest year and feed the schedule', () => {
  assert.equal(postDate({ day: 2, month: 1, year: null, hour: 8, minute: 0 }, new Date('2026-12-30T10:00')), '2027-01-02T08:00');
  assert.equal(postDate({ day: 30, month: 12, year: null, hour: 20, minute: 0 }, new Date('2027-01-02T10:00')), '2026-12-30T20:00');
  assert.equal(postDate({ day: 31, month: 2, year: 2027, hour: 8, minute: 0 }), '');
  const list = { posts: [post(124, { stage: '2 tháng 10, 8:00 CH', icons: ['Alarm'] }), post(123, { stage: '2 tháng 10, 8:00 SA' })] };
  const anchors = postAnchors(list, new Date('2026-10-01T09:00'));
  assert.deepEqual(anchors.map(item => item.gio_dang), ['2026-10-02T20:00', '2026-10-02T08:00']);
  // Folder of 124 is gone and danh_sach.json is missing: TikTok alone anchors every unposted row.
  const rows = [row(125), row(126, { video: '', trang_thai: NO_VIDEO }), row(117)];
  const result = syncSchedule(rows, null, new Date('2026-10-01T09:00'), [...anchors, ...anchors]);
  assert.equal(result.anchor, '2026-10-02T20:00');
  assert.equal(result.anchorFrom, 'tiktok');
  assert.deepEqual(rows.map(item => item.gio_dang), ['2026-10-04T20:00', '2026-10-05T20:00', '2026-10-03T20:00']);
  assert.ok(!result.notes.some(note => note.includes('trùng')));
  const withSlots = [row(125), row(126)];
  syncSchedule(withSlots, { khung_gio: '08:00, 20:00', muc: [] }, new Date('2026-10-01T09:00'), anchors);
  assert.deepEqual(withSlots.map(item => item.gio_dang), ['2026-10-03T08:00', '2026-10-03T20:00']);
});

test('script folders without video merge by folder and pick up the video once rendered', () => {
  const rows = [];
  const scan = video => importQueue([{ thu_muc: 'D:\\kb\\D125 - x', video, tieu_de: '', hashtag: '#MimiAudioSo125',
    trang_thai: video ? 'cho' : NO_VIDEO, variants: video ? { dai: video } : {} }]);
  assert.equal(mergeScan(rows, scan('')).added, 1);
  assert.equal(rowKey(rows[0]), 'd:\\kb\\d125 - x');
  assert.equal(rows[0].trang_thai, NO_VIDEO);
  assert.equal(mergeScan(rows, scan('')).added, 0);
  mergeScan(rows, scan('D:\\kb\\D125 - x\\[Full] v.mp4'));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].video, 'D:\\kb\\D125 - x\\[Full] v.mp4');
  assert.equal(rows[0].trang_thai, 'cho');
  mergeScan(rows, scan(''));
  assert.equal(rows[0].video, 'D:\\kb\\D125 - x\\[Full] v.mp4', 'a missing file keeps the last path');
  rows[0].trang_thai = 'đã lên lịch'; rows[0].statusOrigin = 'tiktok';
  mergeScan(rows, importQueue([{ thu_muc: 'D:\\kb\\D125 - x', video: 'D:\\kb\\D125 - x\\other.mp4', trang_thai: 'đã đăng', statusOrigin: 'receipt' }]));
  assert.equal(rows[0].trang_thai, 'đã lên lịch');
  assert.equal(rows[0].video, 'D:\\kb\\D125 - x\\[Full] v.mp4');
  const pruned = [...rows, { video: '', thu_muc: 'D:\\kb\\E126' }, { video: '', thu_muc: 'E:\\khac\\F1' }];
  assert.equal(pruneMissingFolders(pruned, { ok: true, root: 'D:\\kb', folders_complete: true, folders: ['D:\\kb\\D125 - x'] }), 1);
  assert.deepEqual(pruned.map(item => item.thu_muc), ['D:\\kb\\D125 - x', 'E:\\khac\\F1']);
});

const root = fileURLToPath(new URL('../', import.meta.url));
let context, directory, dashboard, worker, scanData, contentHtml;

const contentPage = (posts, { total = posts.length, initial = posts.length, step = 5 } = {}) => `<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
  <div role="tab">Bài đăng ${total}</div>
  <div id="scroller" style="height:560px;overflow:auto"><div data-tt="components_PostTable_Container" style="position:relative"></div></div>
  <script>
    const posts = ${JSON.stringify(posts)}; let loaded = ${initial};
    const table = document.querySelector('[data-tt="components_PostTable_Container"]'), scroller = document.getElementById('scroller');
    // Virtualized like TikTok: only rows near the viewport exist; more posts load at the bottom.
    function draw() {
      table.style.height = loaded * 120 + 'px'; table.replaceChildren();
      posts.slice(0, loaded).forEach((post, index) => {
        if (index * 120 < scroller.scrollTop - 120 || index * 120 > scroller.scrollTop + 680) return;
        const row = document.createElement('div'); row.dataset.tt = 'components_PostTable_Absolute';
        row.style.cssText = 'position:absolute;left:0;right:0;height:110px;top:' + index * 120 + 'px';
        row.innerHTML = '<div data-tt="components_PostInfoCell_Container"><a data-tt="components_PostInfoCell_a"></a></div><span data-tt="components_PublishStageLabel_TUXText"></span>';
        row.querySelector('a').href = post.url; row.querySelector('a').textContent = post.caption;
        const label = row.querySelector('span'); label.textContent = post.stage;
        for (const name of post.icons) { const icon = document.createElement('span'); icon.dataset.icon = name; label.prepend(icon); }
        table.append(row);
      });
    }
    scroller.addEventListener('scroll', () => {
      if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 50 && loaded < posts.length) loaded = Math.min(posts.length, loaded + ${step});
      draw();
    });
    setTimeout(draw, 400);
  </script></body></html>`;

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'omni-update-'));
  const extension = await isolatedExtension(directory);
  context = await chromium.launchPersistentContext(path.join(directory, 'profile'), { headless: true, channel: 'chromium',
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`] });
  worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  await context.route('https://www.tiktok.com/**', route => route.fulfill({ contentType: 'text/html',
    body: new URL(route.request().url()).pathname === '/tiktokstudio/content' ? contentHtml : '<html><body>upload</body></html>' }));
  await context.route('http://127.0.0.1:8771/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(scanData) }));
  dashboard = await context.newPage();
  await dashboard.goto(`chrome-extension://${new URL(worker.url()).host}/dashboard.html`);
});
after(async () => { await context?.close(); if (directory) await rm(directory, { recursive: true, force: true }); });

test('Cập nhật kịch bản restores deleted rows, lists new scripts and judges posts from the TikTok list', async () => {
  const kb = 'D:\\kb';
  const item = (n, video = true) => ({ thu_muc: `${kb}\\A${n}`, video: video ? `${kb}\\A${n}\\[Full] v.mp4` : '', tieu_de: video ? title(n) : '',
    hashtag: `#MimiAudioSo${n} #truyenaudio`, trang_thai: video ? 'cho' : NO_VIDEO, variants: video ? { dai: `${kb}\\A${n}\\[Full] v.mp4` } : {} });
  scanData = { ok: true, root: kb, folders_complete: true, folders: [124, 125, 126].map(n => `${kb}\\A${n}`),
    muc: [item(124), item(125), item(126, false)], ghi_chu: [], schedule: { khung_gio: '08:00, 20:00', muc: [] } };
  const tomorrow = day(1);
  contentHtml = contentPage([post(124, { stage: shown(tomorrow, '8:00 CH'), icons: ['Alarm'] }), post(123, { stage: shown(day(0), '8:00 SA') })]);
  await dashboard.evaluate(() => chrome.storage.local.clear());
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll('#rows tr').length === 3 && !document.querySelector('#update').disabled);
  assert.match(await dashboard.locator('#rows tr').nth(2).locator('.status').innerText(), /Chưa có video/);
  assert.equal(await dashboard.locator('#rows tr').nth(2).locator('.video-select').inputValue(), '');
  // Deleting hides the row from automatic scans only.
  await dashboard.locator('#rows tr').nth(1).locator('button[title="Xóa dòng"]').click();
  await dashboard.reload();
  await dashboard.waitForFunction(() => document.querySelectorAll('#rows tr').length === 2 && !document.querySelector('#update').disabled);
  const pagesBefore = context.pages().length;
  await dashboard.locator('#update').click();
  await dashboard.waitForFunction(() => /TikTok: đọc/.test(document.querySelector('#scan-status').textContent) && !document.querySelector('#update').disabled);
  const status = await dashboard.locator('#scan-status').innerText();
  assert.match(status, /lấy lại 1 dòng đã xóa/);
  assert.match(status, /đọc 2\/2 bài · đã lên lịch 1 · đã đăng 0 · chưa đăng 2/);
  assert.equal(await dashboard.locator('#update-status').innerText(), status, 'result stays visible on a narrow panel');
  const saved = (await dashboard.evaluate(() => chrome.storage.local.get(['rows', 'tiktokPosts'])));
  const byEpisode = Object.fromEntries(saved.rows.map(item => [item.hashtag.match(/So(\d+)/)[1], item]));
  assert.equal(byEpisode[124].trang_thai, 'đã lên lịch');
  assert.equal(byEpisode[124].gio_dang, tomorrow + 'T20:00');
  assert.equal(byEpisode[125].trang_thai, 'cho');
  assert.equal(byEpisode[126].trang_thai, NO_VIDEO);
  assert.equal(byEpisode[125].gio_dang, day(2) + 'T08:00', 'next slot continues after the latest TikTok schedule');
  assert.equal(byEpisode[126].gio_dang, day(2) + 'T20:00');
  assert.equal(saved.tiktokPosts.posts.length, 2);
  assert.match(await dashboard.locator('#schedule-status').innerText(), /lịch trên TikTok/);
  assert.match(await dashboard.locator('#rows tr').first().locator('.status-source').innerText(), /TikTok/);
  // The temporary Studio tab is closed again.
  for (let wait = 0; wait < 30 && context.pages().length !== pagesBefore; wait++) await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(context.pages().length, pagesBefore);
  assert.ok(!context.pages().some(page => page.url().includes('/tiktokstudio/content')));
  // A rendered video turns the new script into a normal waiting row on the next scan.
  scanData.muc[2] = { ...item(126), tieu_de: title(126) };
  await dashboard.locator('#scan').click();
  await dashboard.waitForFunction(() => !document.querySelector('#scan').disabled);
  const after = (await dashboard.evaluate(() => chrome.storage.local.get('rows'))).rows.find(item => item.hashtag.includes('So126'));
  assert.equal(after.trang_thai, 'cho');
  assert.equal(after.video, `${kb}\\A126\\[Full] v.mp4`);
});

test('reading the post list scrolls a virtualized table only as far as the oldest wanted episode', async () => {
  const posts = Array.from({ length: 15 }, (_, index) => post(115 - index, { stage: shown(day(-index), '8:00 CH') }));
  contentHtml = contentPage(posts, { initial: 5 });
  const read = targets => dashboard.evaluate(targets => chrome.runtime.sendMessage({ type: 'readPosts', targets }), targets);
  const near = await read([{ title: title(113) }]);
  assert.equal(near.ok, true);
  assert.ok(near.list.posts.length < 15, 'stops once the wanted title is found');
  const all = await read([{ title: title(101) }]);
  assert.equal(all.list.posts.length, 15);
  assert.equal(all.list.total, 15);
  assert.equal(all.list.complete, true);
  assert.deepEqual(all.list.posts.map(item => item.id).sort(), posts.map(item => item.id).sort());
  const missing = await read([{ title: 'Full ở Mimi audio Số 200 | Chưa đăng', episode: 200 }]);
  assert.ok(missing.list.posts.length <= 6, 'a newer unposted episode needs no scrolling');
  assert.equal(await dashboard.evaluate(() => chrome.runtime.sendMessage({ type: 'status' }).then(value => value.running)), false);
});

test('the side panel and a separate window stay in sync, and a newly opened window fills dates at once', async () => {
  const kb = 'D:\kb';
  const item = n => ({ thu_muc: `${kb}\A${n}`, video: `${kb}\A${n}\[Full] v.mp4`, tieu_de: title(n), hashtag: `#MimiAudioSo${n}`,
    trang_thai: 'cho', variants: { dai: `${kb}\A${n}\[Full] v.mp4` } });
  scanData = { ok: true, root: kb, folders_complete: true, folders: [`${kb}\A124`, `${kb}\A125`], muc: [item(124), item(125)],
    ghi_chu: [], schedule: { khung_gio: '08:00, 20:00', muc: [] } };
  contentHtml = contentPage([post(124, { stage: shown(day(1), '8:00 CH'), icons: ['Alarm'] })]);
  await dashboard.evaluate(() => chrome.storage.local.clear());
  await dashboard.evaluate(() => chrome.storage.local.set({ scanSettings: { auto: false } }));
  await dashboard.reload();
  const url = dashboard.url();
  const second = await context.newPage(); await second.goto(url);
  const date = (page, n) => page.locator('#rows tr').filter({ hasText: `TẬP ${n}` }).locator('input[type="datetime-local"]').inputValue();
  await dashboard.locator('#update').click();
  await dashboard.waitForFunction(() => /TikTok: đọc/.test(document.querySelector('#update-status').textContent) && !document.querySelector('#update').disabled);
  assert.equal(await date(dashboard, 125), day(2) + 'T08:00');
  // The already open window takes the new list without a reload.
  await second.waitForFunction(() => document.querySelectorAll('#rows tr').length === 2);
  await second.waitForFunction(() => [...document.querySelectorAll('#rows input[type="datetime-local"]')].some(el => el.value));
  assert.equal(await date(second, 124), day(1) + 'T20:00');
  assert.equal(await date(second, 125), day(2) + 'T08:00');
  assert.match(await second.locator('#rows tr').filter({ hasText: 'TẬP 124' }).locator('.status').innerText(), /Đã lên lịch/);
  // Typing in one window reaches the other, and a save there does not wipe it.
  const titleBox = second.locator('#rows tr').filter({ hasText: 'TẬP 125' }).locator('textarea[aria-label="Tiêu đề"]');
  await titleBox.fill('Tiêu đề sửa ở cửa sổ riêng');
  await dashboard.waitForFunction(() => [...document.querySelectorAll('#rows textarea')].some(el => el.value === 'Tiêu đề sửa ở cửa sổ riêng'));
  await second.locator('h1').click();
  await dashboard.locator('#rows tr').filter({ hasText: 'TẬP 125' }).locator('input[type="checkbox"]').check();
  await second.waitForTimeout(300);
  assert.equal(await titleBox.inputValue(), 'Tiêu đề sửa ở cửa sổ riêng');
  // A window opened later recomputes a missing date from the saved TikTok list, with auto-scan off.
  await dashboard.evaluate(async () => {
    const { rows } = await chrome.storage.local.get('rows');
    Object.assign(rows.find(item => item.hashtag.includes('So125')), { gio_dang: '', scheduleKind: 'auto' });
    await chrome.storage.local.set({ rows, rowsStamp: 'test:1' });
  });
  const third = await context.newPage(); await third.goto(url);
  await third.waitForFunction(() => document.querySelectorAll('#rows tr').length === 2);
  assert.equal(await date(third, 125), day(2) + 'T08:00');
  assert.match(await third.locator('#schedule-status').innerText(), /lịch trên TikTok/);
  await second.close(); await third.close();
});

test('the post reader tolerates two tables, thumbnail links and an alarm icon outside the date label', async () => {
  const rowHtml = (n, stage, alarm, iconOutside) => `<div class="r"><a href="/@mimi/video/${7000 + n}"><img alt=""></a>
    <div data-tt="components_PostInfoCell_Container"><a data-tt="components_PostInfoCell_a" href="/@mimi/video/${7000 + n}">${title(n)} #MimiAudioSo${n}</a></div>
    ${alarm && iconOutside ? '<span data-icon="Alarm">!</span>' : ''}
    <div data-tt="components_PublishStageLabel_Container">${alarm && !iconOutside ? '<span data-icon="Alarm">!</span>' : ''}<span data-tt="components_PublishStageLabel_TUXText">${stage}</span></div>
    <button><span data-icon="Edit">e</span></button></div>`;
  contentHtml = `<!doctype html><html><head><meta charset="utf-8"></head><body><div>Bài đăng 3</div>
    <div data-tt="components_PostTable_Container">Nội dung</div>
    <div data-tt="components_PostTable_Container">${rowHtml(124, shown(day(1), '8:00 CH'), true, true)}${rowHtml(123, shown(day(1), '8:00 SA'), true, false)}${rowHtml(122, shown(day(0), '12:00 SA'), false, false)}</div></body></html>`;
  const result = await dashboard.evaluate(() => chrome.runtime.sendMessage({ type: 'readPosts', targets: [] }));
  assert.equal(result.ok, true);
  const byId = Object.fromEntries(result.list.posts.map(item => [item.id, item]));
  assert.deepEqual(Object.keys(byId).sort(), ['7122', '7123', '7124']);
  assert.match(byId[7124].caption, /Số 124/);
  assert.ok(byId[7124].icons.includes('Alarm') && byId[7123].icons.includes('Alarm') && !byId[7122].icons.includes('Alarm'));
  assert.equal(byId[7124].stage, shown(day(1), '8:00 CH'));
  assert.equal(result.list.total, 3);
  const saved = await dashboard.evaluate(() => chrome.storage.local.get('lastPostRead'));
  assert.equal(saved.lastPostRead.ok, true);
  assert.equal(saved.lastPostRead.found, 3);
});

test('a page without posts fails with the page address and keeps a diagnostic', async () => {
  contentHtml = '<!doctype html><html><head><meta charset="utf-8"></head><body>Đang tải trang Studio</body></html>';
  const result = await dashboard.evaluate(() => chrome.runtime.sendMessage({ type: 'readPosts', targets: [] }));
  assert.equal(result.ok, false);
  assert.match(result.error, /sau 30 giây \(trang đang mở: https:\/\/www\.tiktok\.com\/tiktokstudio\/content\)/);
  const { lastPostRead } = await dashboard.evaluate(() => chrome.storage.local.get('lastPostRead'));
  assert.equal(lastPostRead.ok, false);
  assert.equal(lastPostRead.probe.counts.videoLinks, 0);
  assert.match(lastPostRead.probe.text, /Đang tải trang Studio/);
  assert.ok(!context.pages().some(page => page.url().includes('/tiktokstudio/content')));
});
