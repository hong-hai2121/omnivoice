import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import { mkdtemp, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { postTitle, postStage, matchContentPost } from '../extension/posts.js';
import { pageTask } from '../extension/dom.js';
import { episodeKey, TIKTOK_UPLOAD_URL } from '../extension/model.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const title = 'Full ở Mimi audio Số 124 | Sự Thật Đằng Sau Ngày Trở Về Bi Kịch Của Trúc Mã';
const title123 = 'Full ở Mimi audio Số 123 | Màn Cứu Nguy Đầy Kịch Tính Khiến Hôn Phu Trọng Thương';
const date = new Date(Date.now() + 86400_000).toLocaleDateString('en-CA');
const displayedDate = `${Number(date.slice(8))} tháng ${Number(date.slice(5, 7))}, 8:00 CH`;
const sample = { id: '7691247276173315336', url: 'https://www.tiktok.com/@hh129124/video/7691247276173315336', caption: title + ' #MimiAudioSo124  #truyenaudio  #truyenfull  #audio  #fyp', stage: '2 tháng 10, 8:00 CH', icons: ['Alarm'] };
let context, directory, tab, dashboard, tabId, video, contentBody, contentPages = [], uploadVisits = [];

function contentPage(posts, delay = 0) {
  const render = posts => {
    window.contentClicks = 0;
    const unrelated = document.createElement('button'); unrelated.textContent = 'Đăng'; unrelated.onclick = () => window.contentClicks++;
    document.body.append(unrelated);
    const table = document.createElement('div'); table.dataset.tt = 'components_PostTable_Container'; document.body.append(table);
    for (const post of posts) {
      const row = document.createElement('div'); row.dataset.tt = 'components_PostTable_Absolute';
      const cell = document.createElement('div'); cell.dataset.tt = 'components_PostInfoCell_Container';
      const link = document.createElement('a'); link.dataset.tt = 'components_PostInfoCell_a';
      link.href = post.url; link.textContent = post.caption; cell.append(link); row.append(cell);
      const stage = document.createElement('span'); stage.dataset.tt = 'components_PublishStageLabel_TUXText';
      for (const name of post.icons) { const icon = document.createElement('span'); icon.dataset.icon = name; stage.append(icon); }
      const label = document.createElement('span'); label.dataset.tt = 'components_PublishStageLabel_TUXText'; label.textContent = post.stage;
      stage.append(label); row.append(stage); table.append(row);
    }
  };
  return `<html><head><meta charset="utf-8"></head><body><script>setTimeout(()=>(${render.toString()})(${JSON.stringify(posts)}), ${delay});</script></body></html>`;
}
const upload = `<input type="file" accept="video/mp4"><div contenteditable="true" role="textbox" aria-label="Description" style="width:300px;height:80px"></div>
  <label><input type="checkbox" checked id="schedule">Schedule</label><input type="date" aria-label="Date"><input type="time" aria-label="Time">
  <div class="info-progress success" style="height:4px;width:100%"></div><button id="publish">Schedule</button>
  <script>window.clicks=0;document.querySelector('#publish').onclick=()=>{window.clicks++;location.href='/tiktokstudio/content';};</script>`;
const task = (action, data = {}) => tab.evaluate(`(${pageTask.toString()})(${JSON.stringify(action)},${JSON.stringify(data)})`);
const message = request => dashboard.evaluate(request => chrome.runtime.sendMessage(request), request);
const job = () => ({ type: 'prepare', tabId, schedule: true, publish: true, row: { id: '124', video, tieu_de: title, hashtag: '', gio_dang: date + 'T20:00' } });

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'omni-posts-'));
  video = path.join(directory, 'fixture.mp4'); await writeFile(video, 'test bytes');
  const extension = path.join(root, 'extension');
  context = await chromium.launchPersistentContext(path.join(directory, 'profile'), { headless: true, channel: 'chromium',
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`] });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  await context.route('https://www.tiktok.com/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/tiktokstudio/upload') uploadVisits.push(url.href);
    return route.fulfill({ contentType: 'text/html', body: url.pathname === '/tiktokstudio/content' ? contentPages.shift() || contentBody : upload });
  });
  await context.route('http://127.0.0.1:8771/**', route => route.fulfill({ contentType: 'application/json', body: '{"ok":true,"muc":[]}' }));
  tab = await context.newPage(); await tab.goto('https://www.tiktok.com/tiktokstudio/upload');
  dashboard = await context.newPage(); await dashboard.goto(`chrome-extension://${new URL(worker.url()).host}/dashboard.html`);
  await dashboard.locator('#tab option').waitFor({ state: 'attached' }); tabId = Number(await dashboard.locator('#tab').inputValue());
});
beforeEach(async () => {
  await dashboard.evaluate(() => chrome.storage.local.remove(['submissions', 'rowResults', 'progress']));
  contentBody = contentPage([{ ...sample, stage: displayedDate }], 700);
  contentPages = [];
  await tab.goto('https://www.tiktok.com/tiktokstudio/upload');
  uploadVisits = [];
});
after(async () => { await context?.close(); if (directory) await rm(directory, { recursive: true, force: true }); });

test('content title comparison ignores hashtag spacing and Unicode normalization, not episode or variant', () => {
  assert.equal(postTitle(sample.caption.normalize('NFD')), postTitle('  ' + title.replaceAll(' ', '\u200b  ') + '  '));
  assert.equal(matchContentPost([sample], { title }).state, 'matched');
  for (const other of [title123, title.replace('Full', 'Nửa video'), title.replace('124', '1240'), title.slice(0, 25), '']) {
    assert.equal(matchContentPost([sample], { title: other }).state, 'missing');
  }
});
test('content rows distinguish scheduled, published, pending and wrong dates', () => {
  assert.equal(postStage(sample).kind, 'scheduled');
  assert.equal(postStage({ ...sample, icons: [] }).kind, 'published');
  assert.equal(matchContentPost([sample], { title, schedule: true, date: '2026-10-02T20:00' }).state, 'matched');
  assert.equal(matchContentPost([sample], { title, schedule: true, date: '2026-10-02T08:00' }).state, 'mismatch');
  assert.equal(matchContentPost([sample], { title, schedule: false }).state, 'mismatch');
  for (const stage of ['Đang kiểm tra', 'Đang xử lý', 'Bản nháp', 'Đăng thất bại', 'Vi phạm', '']) {
    assert.equal(matchContentPost([{ ...sample, stage, icons: [] }], { title }).state, 'pending');
  }
  assert.equal(postStage({ ...sample, stage: '2 tháng 10, 12:00 SA' }).when.hour, 0);
  assert.equal(postStage({ ...sample, stage: '2 tháng 10, 12:00 CH' }).when.hour, 12);
});
test('duplicate titles stay ambiguous and known old post IDs cannot confirm a repost', () => {
  const second = { ...sample, id: '999', url: 'https://www.tiktok.com/@hh129124/video/999' };
  assert.equal(matchContentPost([sample, second], { title }).state, 'ambiguous');
  assert.equal(matchContentPost([sample], { title, excludeIds: [sample.id] }).state, 'missing');
  assert.equal(matchContentPost([sample, second], { title, excludeIds: [sample.id] }).post.id, second.id);
});
test('DOM reads supplied descendant selectors, ignores outside links, hidden rows and foreign URLs', async () => {
  contentBody = contentPage([sample, { ...sample, id: '123', url: '/@hh129124/video/123', caption: title123 }, { ...sample, url: 'https://other.example/@hh129124/video/555' }]);
  await tab.goto('https://www.tiktok.com/tiktokstudio/content');
  await tab.locator('[data-tt="components_PostTable_Container"]').waitFor();
  await tab.evaluate(() => {
    const first = document.querySelector('[data-tt="components_PostTable_Absolute"]');
    first.after(first.cloneNode(true));
    const hidden = first.cloneNode(true); hidden.style.display = 'none'; hidden.querySelector('a').href = '/@hh129124/video/444'; first.after(hidden);
    document.body.insertAdjacentHTML('beforeend', '<a data-tt="components_PostInfoCell_a" href="/@hh129124/video/222">Unrelated</a>');
  });
  const content = await task('contentPosts'); assert.equal(content.ready, true); assert.equal(content.posts.length, 2);
  assert.deepEqual(content.posts[0], sample); assert.equal(content.posts[1].caption, title123);
  assert.equal(await tab.evaluate(() => window.contentClicks), 0);
  await tab.goto('https://www.tiktok.com/tiktokstudio/upload'); assert.equal((await task('contentPosts')).page, false);
});
test('hard redirect and delayed content list confirm scheduling without a success toast', async () => {
  const result = await message(job()); assert.equal(result.ok, true, result.error);
  assert.equal(new URL(tab.url()).pathname, '/tiktokstudio/content');
  const saved = await dashboard.evaluate(async () => chrome.storage.local.get(['submissions', 'rowResults', 'progress']));
  const receipt = saved.submissions[episodeKey(video)];
  assert.equal(receipt.state, 'success'); assert.equal(receipt.postEvidence.id, sample.id);
  assert.equal(receipt.postEvidence.kind, 'scheduled'); assert.equal(receipt.postEvidence.url, sample.url);
  assert.equal(saved.rowResults['124'].trang_thai, 'done'); assert.match(saved.progress.log.at(-1), /đã lên lịch/);
  assert.equal(await tab.evaluate(() => window.contentClicks), 0);
});
test('prepare from content returns to the requested upload URL without taking the active tab', async () => {
  await tab.goto('https://www.tiktok.com/tiktokstudio/content');
  await dashboard.bringToFront();
  const active = await dashboard.evaluate(async () => (await chrome.tabs.query({ active: true, currentWindow: true }))[0].id);
  const result = await message({ ...job(), publish: false }); assert.equal(result.ok, true, result.error);
  assert.equal(tab.url(), TIKTOK_UPLOAD_URL); assert.deepEqual(uploadVisits, [TIKTOK_UPLOAD_URL]);
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files[0].name), 'fixture.mp4');
  assert.equal(await tab.locator('[role="textbox"]').innerText(), title);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  assert.equal(await dashboard.evaluate(async () => (await chrome.tabs.query({ active: true, currentWindow: true }))[0].id), active);
});
test('a separate new-video request after success automatically leaves content and completes the next post', async () => {
  const first = await message(job()); assert.equal(first.ok, true, first.error);
  assert.equal(new URL(tab.url()).pathname, '/tiktokstudio/content');
  const folder = path.join(directory, 'next-request'); await mkdir(folder, { recursive: true });
  const nextVideo = path.join(folder, 'next.mp4'); await writeFile(nextVideo, 'next bytes');
  const next = job(); next.row = { ...next.row, id: 'next', video: nextVideo, tieu_de: title123 };
  contentBody = contentPage([{ ...sample, id: '123', url: '/@hh129124/video/123', caption: title123, stage: displayedDate }]);
  const second = await message(next); assert.equal(second.ok, true, second.error);
  assert.deepEqual(uploadVisits, [TIKTOK_UPLOAD_URL]);
  const receipts = await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions);
  assert.equal(receipts[episodeKey(video)].state, 'success'); assert.equal(receipts[episodeKey(nextVideo)].state, 'success');
});
test('invalid jobs and repeated submissions are rejected before leaving content', async () => {
  await tab.goto('https://www.tiktok.com/tiktokstudio/content');
  const invalid = job(); invalid.row.gio_dang = '2020-01-01T20:00';
  assert.equal((await message(invalid)).ok, false);
  const row = job().row;
  await dashboard.evaluate(({ key, row }) => chrome.storage.local.set({ submissions: { [key]: { state: 'success', video: row.video, date: row.gio_dang } } }), { key: episodeKey(video), row });
  assert.equal((await message(job())).ok, false);
  assert.equal(new URL(tab.url()).pathname, '/tiktokstudio/content'); assert.deepEqual(uploadVisits, []);
});
test('prepare on an existing upload page never reloads or discards the loaded draft', async () => {
  assert.equal((await message({ ...job(), publish: false })).ok, true);
  await tab.evaluate(() => { window.draftMarker = 'keep'; });
  const repeat = await message({ ...job(), publish: false, freshUpload: true }); assert.equal(repeat.ok, false);
  assert.equal(await tab.evaluate(() => window.draftMarker), 'keep');
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files[0].name), 'fixture.mp4');
  assert.deepEqual(uploadVisits, []);
});
test('stopping while the upload navigation is loading prevents file assignment and publishing', async () => {
  await tab.goto('https://www.tiktok.com/tiktokstudio/content');
  let release, started;
  const held = new Promise(resolve => { release = resolve; }), reached = new Promise(resolve => { started = resolve; });
  const slowRoute = async route => { started(); await held; await route.fulfill({ contentType: 'text/html', body: upload }); };
  await tab.route(TIKTOK_UPLOAD_URL, slowRoute);
  const running = message({ ...job(), publish: false });
  try {
    await reached;
    await message({ type: 'stop' });
    const result = await running; assert.equal(result.ok, false); assert.match(result.error, /Da dung/);
    release();
    await tab.locator('[type="file"]').waitFor();
    assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files.length), 0);
    assert.equal(await tab.evaluate(() => window.clicks), 0);
  } finally { release(); await message({ type: 'stop' }); await running; await tab.unroute(TIKTOK_UPLOAD_URL, slowRoute); }
});
test('SPA redirect confirms a published video, keeping its full title evidence', async () => {
  await tab.evaluate(body => {
    document.querySelector('#publish').textContent = 'Đăng';
    document.querySelector('#publish').onclick = () => {
      history.pushState({}, '', '/tiktokstudio/content');
      document.open(); document.write(body); document.close();
    };
  }, contentPage([{ ...sample, icons: [] }]));
  await tab.locator('#schedule').uncheck();
  const request = job(); request.schedule = false; request.row.gio_dang = '';
  const result = await message(request); assert.equal(result.ok, true, result.error);
  const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(receipt.state, 'success'); assert.equal(receipt.postEvidence.kind, 'published');
});
test('unmatched content remains uncertain and stop cancels verification without another click', async () => {
  contentBody = contentPage([{ ...sample, caption: title123, stage: displayedDate }]);
  const running = message(job());
  try {
    await expect.poll(() => dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress?.log.at(-1)?.includes('Đã chuyển sang Nội dung'))).toBe(true);
    const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
    assert.equal(receipt.state, 'uncertain'); assert.equal(receipt.postEvidence, undefined);
    await message({ type: 'stop' }); const result = await running; assert.equal(result.ok, false);
    assert.equal(await tab.evaluate(() => window.contentClicks), 0);
  } finally { await message({ type: 'stop' }); await running; }
});
test('upload iframe navigation can destroy the old editor context before content verification', async () => {
  await tab.setContent('<iframe style="width:600px;height:400px"></iframe>');
  await tab.frames()[1].setContent(upload.replace("location.href='/tiktokstudio/content'", "top.location.href='/tiktokstudio/content'"));
  const result = await message(job()); assert.equal(result.ok, true, result.error);
  const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(receipt.postEvidence.id, sample.id);
});
test('queue moves to the next upload only after matching the redirected content row', async () => {
  const folder = path.join(directory, 'second'); await mkdir(folder, { recursive: true });
  const secondVideo = path.join(folder, 'second.mp4'); await writeFile(secondVideo, 'test bytes');
  const request = job(), second = { ...request.row, id: 'second', tieu_de: title123, video: secondVideo };
  contentPages = [contentBody, contentPage([{ ...sample, id: '123', url: '/@hh129124/video/123', caption: title123, stage: displayedDate }], 500)];
  request.rows = [request.row, second];
  const result = await message(request); assert.equal(result.ok, true, result.error);
  const receipts = await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions);
  assert.equal(receipts[episodeKey(video)].postEvidence.id, sample.id);
  assert.equal(receipts[episodeKey(secondVideo)].postEvidence.id, '123');
  assert.equal(receipts[episodeKey(secondVideo)].state, 'success');
  assert.deepEqual(uploadVisits, [TIKTOK_UPLOAD_URL]);
});
test('confirmation click followed by a redirect is verified against the content table', async () => {
  await tab.evaluate(() => {
    document.querySelector('#publish').onclick = () => {
      const dialog = document.createElement('div'); dialog.setAttribute('role', 'dialog');
      dialog.innerHTML = '<h2>Tiếp tục đăng?</h2><p>Chúng tôi vẫn đang kiểm tra video của bạn để phát hiện xem có vấn đề tiềm ẩn hay không. Bạn có muốn tiếp tục đăng trước khi quy trình kiểm tra hoàn tất không?</p><button>Hủy</button><button id="confirm">Đăng ngay</button>';
      document.body.append(dialog); dialog.querySelector('#confirm').onclick = () => { location.href = '/tiktokstudio/content'; };
    };
  });
  const result = await message(job()); assert.equal(result.ok, true, result.error);
  const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(receipt.confirmation.state, 'attempted'); assert.equal(receipt.postEvidence.id, sample.id);
});
test('manual missing and ambiguous rows preserve prior success receipts and never publish', async () => {
  contentBody = contentPage([sample, { ...sample, id: '555', url: '/@hh129124/video/555' }]);
  await tab.goto('https://www.tiktok.com/tiktokstudio/content');
  const row = { ...job().row, trang_thai: 'done' }, key = episodeKey(video);
  const receipt = { state: 'success', video, postEvidence: sample }, result = { trang_thai: 'done', ghi_chu: 'Existing confirmation' };
  await dashboard.evaluate(({ key, receipt, id, result }) => chrome.storage.local.set({ submissions: { [key]: receipt }, rowResults: { [id]: result } }), { key, receipt, id: row.id, result });
  for (const tieu_de of [title, 'Missing']) {
    const checked = await message({ type: 'checkPosts', tabId, rows: [{ ...row, tieu_de }] }); assert.equal(checked.ok, true, checked.error);
    const saved = await dashboard.evaluate(async () => chrome.storage.local.get(['submissions', 'rowResults']));
    assert.deepEqual(saved.submissions[key], receipt); assert.deepEqual(saved.rowResults[row.id], result);
  }
  assert.equal(await tab.evaluate(() => window.contentClicks), 0);
});
test('manual content check updates only selected matches and never clicks or requires a future schedule', async () => {
  contentBody = contentPage([sample, { ...sample, id: '123', url: '/@hh129124/video/123', caption: title123, icons: [] }]);
  await tab.goto('https://www.tiktok.com/tiktokstudio/content');
  const first = { ...job().row, gio_dang: '2020-01-01T00:00', trang_thai: 'error' };
  const missing = { ...first, id: 'missing', tieu_de: 'Missing title', video: 'D:\\missing\\x.mp4' };
  const unselected = { ...first, id: '123', tieu_de: title123, video: 'D:\\123\\x.mp4' };
  await dashboard.evaluate(({ first, missing, unselected }) => chrome.storage.local.set({ rows: [first, missing, unselected], checkedIds: [first.id, missing.id], scanSettings: { auto: false } }), { first, missing, unselected });
  await dashboard.reload(); await expect(dashboard.locator('#check-posts')).toBeEnabled();
  await dashboard.locator('#repost').check(); await dashboard.locator('#check-posts').click();
  await expect.poll(() => dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress?.status)).toBe('done');
  const saved = await dashboard.evaluate(async () => chrome.storage.local.get(['submissions', 'rowResults']));
  assert.equal(saved.rowResults[first.id].trang_thai, 'done'); assert.equal(saved.rowResults[missing.id].trang_thai, 'review');
  assert.equal(saved.rowResults[unselected.id], undefined); assert.equal(saved.submissions[episodeKey(video)].postEvidence.id, sample.id);
  assert.equal(await tab.evaluate(() => window.contentClicks), 0);
  assert.equal(new URL(tab.url()).pathname, '/tiktokstudio/content');
  for (const [name, width] of [['content-check-desktop', 1280], ['content-check-mobile', 390]]) {
    await dashboard.setViewportSize({ width, height: 900 }); await expect(dashboard.locator('#check-posts')).toBeVisible();
    assert.equal(await dashboard.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await mkdir(path.join(root, 'test-results'), { recursive: true });
    await dashboard.screenshot({ path: path.join(root, 'test-results', name + '.png'), fullPage: true });
  }
});
