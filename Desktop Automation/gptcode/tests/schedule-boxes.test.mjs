/* TikTok Studio from October 2026: the schedule date and time are plain boxes
   (<div class="… date-picker-input">2026-10-27</div>, <div class="… time-picker-input"><span>20:00</span></div>)
   instead of readonly inputs; the calendar and time popups are unchanged. */
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pageTask } from '../extension/dom.js';
import { isolatedExtension } from './helpers.mjs';

const calendarHTML = await readFile(new URL('./tiktok-calendar.fixture.html', import.meta.url), 'utf8');
const timeHTML = await readFile(new URL('./tiktok-time.fixture.html', import.meta.url), 'utf8');
let context, directory, tab, dashboard, tabId, video;
const iso = value => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
const task = (action, data = {}) => tab.evaluate(`(${pageTask.toString()})(${JSON.stringify(action)},${JSON.stringify(data)})`);
const message = request => dashboard.evaluate(request => chrome.runtime.sendMessage(request), request);
const job = date => ({ type: 'prepare', tabId, row: { id: 'boxes', video, tieu_de: 'Test', hashtag: '', gio_dang: date + 'T20:15' }, schedule: true, publish: true });

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'omni-boxes-'));
  video = path.join(directory, 'fixture.mp4'); await writeFile(video, 'test file bytes');
  const extension = await isolatedExtension(directory);
  context = await chromium.launchPersistentContext(path.join(directory, 'profile'), {
    headless: true, channel: 'chromium', args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  await context.route('https://www.tiktok.com/**', route => route.fulfill({ contentType: 'text/html', body: '<html><body></body></html>' }));
  await context.route('http://127.0.0.1:8771/**', route => route.fulfill({ contentType: 'application/json', body: '{"ok":true,"muc":[]}' }));
  tab = await context.newPage(); await tab.goto('https://www.tiktok.com/tiktokstudio/upload');
  dashboard = await context.newPage(); await dashboard.goto(`chrome-extension://${new URL(worker.url()).host}/dashboard.html`);
  await dashboard.locator('#tab option').waitFor({ state: 'attached' });
  tabId = Number(await dashboard.locator('#tab').inputValue());
});
beforeEach(async () => {
  await dashboard.evaluate(() => chrome.storage.local.remove(['submissions', 'progress', 'rowResults']));
  await tab.goto('https://www.tiktok.com/tiktokstudio/upload');
});
after(async () => {
  await context?.close();
  if (directory) await rm(directory, { recursive: true, force: true });
});

// named: boxes carry TikTok's date-picker-input / time-picker-input classes; otherwise only their text identifies them.
async function mount(options = {}) {
  const config = { shown: '2026-09-01', selected: '2026-09-30', minimum: '2026-09-30', time: '11:05', named: true, delay: 0, ...options };
  const dateClass = config.named ? 'jsx-77 date-picker-input' : 'jsx-77 schedule-date';
  const timeClass = config.named ? 'jsx-77 time-picker-input' : 'jsx-77 schedule-time';
  await tab.setContent(`<style>
    body { font:14px Arial; margin:24px; color:#222; }
    .pickers { display:flex; gap:24px; align-items:flex-start; } .box { border:1px solid #ccc; padding:8px; width:160px; cursor:pointer; }
    .calendar-wrapper, .tiktok-timepicker-time-picker-container { position:static!important; border:1px solid #ccc; }
    .month-header-wrapper { display:flex; justify-content:space-between; padding:12px; }
    .days-wrapper, .day-header-wrapper { display:grid; grid-template-columns:repeat(7, 50px); text-align:center; }
    .day { display:inline-block; padding:8px; color:#999; } .day.valid { color:#222; } .day.selected { background:#eee; }
    .tiktok-timepicker-time-scroll-container { display:inline-block; width:70px; height:230px; overflow:auto; }
    .tiktok-timepicker-option-item { padding:6px; }
  </style><input type="file" accept="video/mp4">
    <div class="jsx-77">Thời lượng: 38m41s · 2026-01-01</div>
    <div contenteditable="true" role="textbox" aria-label="Description" style="height:50px"></div>
    <div class="jsx-77 form"><div class="jsx-77 post-mode">
    <label><input type="radio" name="post-mode" class="Radio__input" value="post_now">Bây giờ</label>
    <label><input type="radio" name="post-mode" class="Radio__input" value="schedule" checked>Lên lịch</label></div>
    <div class="jsx-77 pickers">
      <div class="jsx-77"><div id="date-box" class="box ${dateClass}"><span class="jsx-77">${config.selected}</span><svg width="12" height="12"><path d="M0 0h12v12H0z"/></svg></div>${calendarHTML}</div>
      <div class="jsx-77"><div id="time-box" class="box ${timeClass}"><span class="jsx-77">${config.time}</span><svg width="12" height="12"><path d="M0 0h12v12H0z"/></svg></div>${timeHTML}</div>
    </div>
    <div class="jsx-77 timezone"><span class="jsx-77">(GMT+7) Giờ địa phương</span></div></div>
    <div class="info-progress success" style="width:100%;height:4px;visibility:visible"></div>
    <button id="publish" data-e2e="post_video_button">Lên lịch</button><div role="status" id="outcome"></div>`);
  await tab.evaluate(config => {
    const calendar = document.querySelector('.calendar-wrapper'), picker = document.querySelector('.tiktok-timepicker-time-picker-container');
    const dateText = document.querySelector('#date-box span'), timeText = document.querySelector('#time-box span');
    calendar.hidden = true; picker.hidden = true;
    window.clicks = 0; window.navigation = []; window.chosenDates = []; window.opened = { date: 0, time: 0 };
    let shown = new Date(config.shown + 'T12:00');
    const iso = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const months = ['Tháng Một', 'Tháng Hai', 'Tháng Ba', 'Tháng Tư', 'Tháng Năm', 'Tháng Sáu', 'Tháng Bảy', 'Tháng Tám', 'Tháng Chín', 'Tháng Mười', 'Tháng Mười Một', 'Tháng Mười Hai'];
    const render = () => {
      calendar.querySelector('.month-title').textContent = months[shown.getMonth()];
      calendar.querySelector('.year-title').textContent = shown.getFullYear();
      calendar.querySelectorAll('.days-wrapper').forEach(row => row.remove());
      const year = shown.getFullYear(), month = shown.getMonth(), offset = new Date(year, month, 1).getDay();
      const count = Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7;
      for (let i = 0; i < count; i += 7) {
        const row = document.createElement('div'); row.className = 'jsx-1793871833 days-wrapper';
        for (let j = 0; j < 7; j++) {
          const day = new Date(year, month, 1 - offset + i + j), value = iso(day);
          const container = document.createElement('div'); container.className = 'jsx-1793871833 day-span-container';
          const cell = document.createElement('span'); cell.className = 'jsx-1793871833 day'; cell.textContent = day.getDate();
          if (value >= config.minimum) cell.classList.add('valid');
          if (value === dateText.textContent) cell.classList.add('selected');
          cell.onclick = () => {
            window.chosenDates.push(value);
            if (!cell.classList.contains('valid')) return;
            dateText.textContent = value; calendar.hidden = true;
          };
          container.append(cell); row.append(container);
        }
        calendar.append(row);
      }
    };
    render();
    calendar.querySelectorAll('.arrow').forEach((arrow, i) => {
      arrow.onclick = () => {
        const direction = i ? 1 : -1; window.navigation.push(direction);
        setTimeout(() => { shown = new Date(shown.getFullYear(), shown.getMonth() + direction, 1); render(); }, config.delay);
      };
    });
    document.querySelector('#date-box').onclick = () => { window.opened.date++; setTimeout(() => { calendar.hidden = !calendar.hidden; picker.hidden = true; }, config.delay); };
    document.querySelector('#time-box').onclick = () => { window.opened.time++; setTimeout(() => { picker.hidden = !picker.hidden; calendar.hidden = true; }, config.delay); };
    for (const span of picker.querySelectorAll('.tiktok-timepicker-option-text')) span.onclick = () => {
      const hour = span.classList.contains('tiktok-timepicker-left');
      setTimeout(() => {
        const parts = timeText.textContent.split(':'); parts[hour ? 0 : 1] = span.textContent;
        timeText.textContent = parts.join(':');
        if (hour) picker.hidden = true;
      }, config.delay);
    };
    document.querySelector('#publish').onclick = () => { window.clicks++; document.querySelector('#outcome').textContent = 'Video has been scheduled'; };
  }, config);
}

test('date and time boxes without inputs are the schedule fields', async () => {
  await mount();
  assert.equal(await task('schedule'), 'already');
  assert.equal(await task('scheduleReady'), true);
  const state = await task('scheduleSnapshot');
  assert.equal(state.date.value, '2026-09-30'); assert.equal(state.date.readonly, true); assert.equal(state.date.type, 'div');
  assert.equal(state.time.value, '11:05'); assert.equal(state.time.readonly, true);
  assert.equal(await task('dateCheck', { date: '2026-09-30' }), true);
  assert.equal(await task('dateCheck', { date: '2026-01-01' }), false, 'the duration line before the radios is not the date box');
  assert.equal(await task('timeCheck', { time: '11:05' }), true);
  assert.equal(await task('timePartCheck', { part: 'minute', value: '05' }), true);
  assert.equal(await task('scheduleCheck', { date: '2026-09-30', time: '11:05' }), true);
  assert.equal(await task('immediateCheck'), false);
  await assert.rejects(() => task('setTime', { value: '08:00' }), /chi doc/);
  const inspected = await task('inspect');
  assert.match(inspected.scheduleHtml, /date-picker-input/);
  assert.match(inspected.scheduleHtml, /time-picker-input/);
  assert.doesNotMatch(inspected.scheduleHtml, /<path/);
  assert.ok(inspected.controls.some(control => /date-picker-input/.test(control.class)));
  assert.equal(await task('revealSchedule'), true);
});

test('boxes identified by their text alone still work, a box before the radios does not', async () => {
  await mount({ named: false });
  assert.equal(await task('scheduleReady'), true);
  assert.equal((await task('scheduleSnapshot')).date.value, '2026-09-30');
  assert.equal(await task('timeCheck', { time: '11:05' }), true);
  await task('openDate', { date: '2026-09-30' });
  await expect(tab.locator('.calendar-wrapper')).toBeVisible();
  assert.equal(await tab.evaluate(() => window.opened.date), 1);
});

test('real extension schedules through the boxes: opens popups, moves a month, reopens minutes and posts', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const priorMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() - 1, 1));
  await mount({ shown: priorMonth, selected: priorMonth, minimum: priorMonth, delay: 300 });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.equal(await task('scheduleCheck', { date: target, time: '20:15' }), true);
  assert.equal(await tab.locator('#date-box').innerText(), target);
  assert.equal(await tab.locator('#time-box').innerText(), '20:15');
  assert.deepEqual(await tab.evaluate(() => window.navigation), [1]);
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), [target]);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 1, time: 2 });
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test('already correct boxes are left alone and the diagnostic of a failure shows the block', async () => {
  const target = iso(new Date(Date.now() + 86400_000));
  await mount({ shown: target, selected: target, minimum: target, time: '20:15' });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 0, time: 0 });
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  await tab.evaluate(() => { document.querySelector('#date-box').remove(); });
  await dashboard.evaluate(() => chrome.storage.local.remove(['submissions']));
  const failed = await message({ ...job(target), type: 'fill' });
  assert.equal(failed.ok, false); assert.match(failed.error, /Chua tim thay o ngay\/gio/);
  const { lastDiagnostic } = await dashboard.evaluate(() => chrome.storage.local.get('lastDiagnostic'));
  assert.match(lastDiagnostic.frames[0].scheduleHtml, /time-picker-input/);
  assert.equal(lastDiagnostic.frames[0].schedule.date, null);
  assert.equal(lastDiagnostic.frames[0].schedule.time.value, '20:15');
});
