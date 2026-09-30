import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import { readFile, mkdtemp, writeFile, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pageTask } from '../extension/dom.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const calendarHTML = await readFile(new URL('./tiktok-calendar.fixture.html', import.meta.url), 'utf8');
const timeHTML = await readFile(new URL('./tiktok-time.fixture.html', import.meta.url), 'utf8');
let context, directory, tab, dashboard, tabId, video;
const iso = value => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
const task = (action, data = {}) => tab.evaluate(`(${pageTask.toString()})(${JSON.stringify(action)},${JSON.stringify(data)})`);
const message = request => dashboard.evaluate(request => chrome.runtime.sendMessage(request), request);
const job = date => ({ type: 'prepare', tabId, row: { id: 'calendar', video, tieu_de: 'Test', hashtag: '', gio_dang: date + 'T20:15' }, schedule: true, publish: true });

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'omni-calendar-'));
  video = path.join(directory, 'fixture.mp4'); await writeFile(video, 'test file bytes');
  const extension = path.join(root, 'extension');
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

async function mount(options = {}) {
  const config = { shown: '2026-09-01', selected: '2026-09-30', minimum: '2026-09-30', delay: 0, original: false, ...options };
  await tab.setContent(`<style>
    body { font:14px Arial; margin:24px; color:#222; }
    .scheduled-picker { display:flex; gap:24px; align-items:flex-start; }
    .TUXFormField { width:176px; padding:8px 0; } input { font:inherit; padding:8px; }
    .calendar-wrapper, .tiktok-timepicker-time-picker-container { position:static!important; border:1px solid #ccc; }
    .month-header-wrapper { display:flex; justify-content:space-between; padding:12px; }
    .days-wrapper, .day-header-wrapper { display:grid; grid-template-columns:repeat(7, 50px); text-align:center; }
    .day { display:inline-block; padding:8px; color:#999; } .day.valid { color:#222; } .day.selected { background:#eee; }
    .tiktok-timepicker-time-scroll-container { display:inline-block; width:70px; height:230px; overflow:auto; }
    .tiktok-timepicker-option-item { padding:6px; }
  </style><input type="file" accept="video/mp4">
    <div contenteditable="true" role="textbox" aria-label="Description" style="height:50px"></div>
    <label><input type="radio" name="post-mode" class="Radio__input" value="post_now">B\u00e2y gi\u1edd</label>
    <label><input type="radio" name="post-mode" class="Radio__input" value="schedule" checked>L\u00ean l\u1ecbch</label>
    <div class="scheduled-picker">
      <div><div id="time-trigger" class="jsx-2483585186"><div class="TUXFormField TUXTextInput"><div class="TUXInputBox"><div class="TUXTextInputCore"><input class="TUXTextInputCore-input" id="time" type="text" readonly value="11:05"></div></div></div></div>${timeHTML}</div>
      <div><div id="date-trigger" class="jsx-2483585186"><div class="TUXFormField TUXTextInput"><div class="TUXInputBox"><div class="TUXTextInputCore"><input class="TUXTextInputCore-input" id="date" type="text" readonly value="${config.selected}"></div></div></div></div>${calendarHTML}</div>
    </div><div class="info-progress success" style="width:100%;height:4px;visibility:visible"></div>
    <button id="publish" data-e2e="post_video_button">Schedule</button><div role="status" id="outcome"></div>`);
  await tab.evaluate(config => {
    const calendar = document.querySelector('.calendar-wrapper'), picker = document.querySelector('.tiktok-timepicker-time-picker-container');
    const dateInput = document.querySelector('#date'), timeInput = document.querySelector('#time');
    calendar.hidden = true; picker.hidden = true;
    window.clicks = 0; window.navigation = []; window.chosenDates = []; window.opened = { date: 0, time: 0 }; window.inputClicks = 0;
    let shown = new Date(config.shown + 'T12:00');
    const iso = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const months = ['Th\u00e1ng M\u1ed9t', 'Th\u00e1ng Hai', 'Th\u00e1ng Ba', 'Th\u00e1ng T\u01b0', 'Th\u00e1ng N\u0103m', 'Th\u00e1ng S\u00e1u', 'Th\u00e1ng B\u1ea3y', 'Th\u00e1ng T\u00e1m', 'Th\u00e1ng Ch\u00edn', 'Th\u00e1ng M\u01b0\u1eddi', 'Th\u00e1ng M\u01b0\u1eddi M\u1ed9t', 'Th\u00e1ng M\u01b0\u1eddi Hai'];
    const bindDays = () => {
      const year = shown.getFullYear(), month = shown.getMonth(), offset = new Date(year, month, 1).getDay();
      calendar.querySelectorAll('.days-wrapper .day').forEach((cell, i) => {
        cell.onclick = () => {
          const chosen = iso(new Date(year, month, 1 - offset + i));
          window.chosenDates.push(chosen);
          if (!cell.classList.contains('valid')) return;
          if (!config.ignoreDate) dateInput.value = chosen;
          calendar.hidden = true;
        };
      });
    };
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
          if (value >= config.minimum && (!config.maximum || value <= config.maximum)) cell.classList.add('valid');
          if (value === dateInput.value) cell.classList.add('selected');
          container.append(cell); row.append(container);
        }
        calendar.append(row);
      }
      bindDays();
    };
    if (config.original) bindDays(); else render();
    calendar.querySelectorAll('.arrow').forEach((arrow, i) => {
      arrow.onclick = () => {
        const direction = i ? 1 : -1; window.navigation.push(direction);
        if (config.stuck) return;
        setTimeout(() => { shown = new Date(shown.getFullYear(), shown.getMonth() + direction, 1); render(); }, config.delay);
      };
    });
    // Input clicks deliberately do not bubble: only the supplied wrapper opens the popup.
    for (const input of [dateInput, timeInput]) input.onclick = event => { window.inputClicks++; event.stopPropagation(); };
    document.querySelector('#date-trigger').onclick = () => { window.opened.date++; setTimeout(() => { calendar.hidden = !calendar.hidden; picker.hidden = true; }, config.delay); };
    document.querySelector('#time-trigger').onclick = () => { window.opened.time++; setTimeout(() => { picker.hidden = !picker.hidden; calendar.hidden = true; }, config.delay); };
    for (const span of picker.querySelectorAll('.tiktok-timepicker-option-text')) span.onclick = () => {
      const hour = span.classList.contains('tiktok-timepicker-left');
      setTimeout(() => {
        const parts = timeInput.value.split(':'); parts[hour ? 0 : 1] = span.textContent;
        if (!config.ignoreTime) timeInput.value = parts.join(':');
        if (hour && config.closeHour) picker.hidden = true;
      }, config.delay);
    };
    document.querySelector('#publish').onclick = () => { window.clicks++; document.querySelector('#outcome').textContent = 'Video has been scheduled'; };
  }, config);
}

test('Vietnamese post-now radio must not be mistaken for the time field', async () => {
  await mount();
  await tab.locator('#time').evaluate(el => { el.value = '14:20'; });
  assert.equal(await task('schedule'), 'already');
  assert.equal(await task('scheduleReady'), true);
  const state = await task('scheduleSnapshot');
  assert.equal(state.time.value, '14:20');
  assert.equal(state.date.value, '2026-09-30');
  assert.equal(await tab.locator('[value="post_now"]').isChecked(), false);
  assert.equal(await tab.locator('[value="schedule"]').isChecked(), true);
});

test('date and time labels on binary controls do not count as date/time inputs', async () => {
  await tab.setContent('<label><input type="checkbox" checked>Time</label>' +
    '<label><input type="radio">Date</label><input role="switch" aria-label="Time">' +
    '<input type="button" aria-label="Date"><input type="submit" aria-label="Time">');
  assert.equal(await task('scheduleReady'), false);
  assert.equal((await task('scheduleSnapshot')).date, null);
  assert.equal((await task('scheduleSnapshot')).time, null);
  await tab.evaluate(() => {
    document.body.insertAdjacentHTML('beforeend', '<input type="date" value="2026-09-30"><input type="time" value="14:20">');
  });
  assert.equal(await task('scheduleReady'), true);
  // Multiple genuine time fields must still fail instead of choosing arbitrarily.
  await tab.evaluate(() => document.body.insertAdjacentHTML('beforeend', '<input type="text" readonly value="15:00">'));
  assert.equal(await task('scheduleReady'), false);
});

test('a TikTok invisible time popup must be opened even when it still has layout rectangles', async () => {
  await mount();
  await tab.evaluate(() => {
    const picker = document.querySelector('.tiktok-timepicker-time-picker-container');
    picker.hidden = false; picker.classList.add('tiktok-timepicker-invisible');
    picker.style.opacity = '0'; picker.style.pointerEvents = 'none';
    document.querySelector('#time-trigger').onclick = () => {
      window.opened.time++;
      picker.classList.remove('tiktok-timepicker-invisible'); picker.style.opacity = '1'; picker.style.pointerEvents = 'auto';
    };
  });
  assert.equal(await task('timePickerReady'), false);
  assert.equal(await task('pickTime', { part: 'hour', value: '08' }), false);
  assert.equal(await task('openTime'), true);
  assert.equal(await tab.evaluate(() => window.opened.time), 1);
  assert.equal(await task('timePickerReady'), true);
  assert.equal(await task('pickTime', { part: 'hour', value: '08' }), true);
  assert.equal(await task('pickTime', { part: 'minute', value: '00' }), true);
  await expect(tab.locator('#time')).toHaveValue('08:00');
});

test('reported Vietnamese controls complete scheduling but cannot publish at 15.57 percent upload', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const priorMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() - 1, 1));
  await mount({ shown: priorMonth, selected: priorMonth, minimum: priorMonth });
  await tab.evaluate(() => {
    const picker = document.querySelector('.tiktok-timepicker-time-picker-container');
    picker.hidden = false; picker.classList.add('tiktok-timepicker-invisible');
    picker.style.opacity = '0'; picker.style.pointerEvents = 'none';
    document.querySelector('#time').value = '14:20';
    document.querySelector('#time-trigger').onclick = () => {
      window.opened.time++;
      picker.hidden = false;
      picker.classList.remove('tiktok-timepicker-invisible'); picker.style.opacity = '1'; picker.style.pointerEvents = 'auto';
    };
    const progress = document.querySelector('.info-progress');
    progress.classList.remove('success'); progress.style.width = '15.57%';
  });
  const request = job(target); request.row.gio_dang = target + 'T08:00';
  const running = message(request);
  try {
    await expect.poll(() => dashboard.evaluate(async () => {
      const { progress } = await chrome.storage.local.get('progress');
      return progress?.status === 'running' && progress.log.at(-1).includes('Dang cho tai/xu ly');
    }), { timeout: 15_000 }).toBe(true);
    assert.equal(await task('scheduleCheck', { date: target, time: '08:00' }), true);
    assert.equal(await tab.locator('[value="schedule"]').isChecked(), true);
    assert.equal(await tab.locator('[value="post_now"]').isChecked(), false);
    assert.equal(await tab.evaluate(() => window.opened.time), 1);
    assert.equal(await tab.evaluate(() => window.clicks), 0);
    await tab.locator('.info-progress').evaluate(el => { el.style.width = '100%'; el.classList.add('success'); });
    const result = await running; assert.equal(result.ok, true, result.error);
    assert.equal(await tab.evaluate(() => window.clicks), 1);
  } finally {
    await message({ type: 'stop' }); await running;
  }
});

test('supplied September popup distinguishes August 30 from September 30 and October 1', async () => {
  await mount({ original: true });
  await task('openDate', { date: '2026-09-30' });
  await expect(tab.locator('.calendar-wrapper')).toBeVisible();
  const state = await task('calendarState');
  assert.equal(state.month, 9); assert.equal(state.year, 2026); assert.equal(state.gridValid, true);
  assert.equal(await task('pickDate', { value: '2026-10-01' }), 'missing');
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), []);
  assert.equal(await task('pickDate', { value: '2026-09-30' }), 'picked');
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), ['2026-09-30']);
  assert.equal(await tab.locator('#date').getAttribute('readonly'), '');
  assert.equal(await tab.evaluate(() => window.inputClicks), 0);
});

test('disabled, malformed and ambiguous calendars do not click a day', async () => {
  await mount({ original: true }); await task('openDate'); await expect(tab.locator('.calendar-wrapper')).toBeVisible();
  await assert.rejects(() => task('pickDate', { value: '2026-09-29' }), /bi TikTok khoa/);
  await tab.locator('.day').first().evaluate(el => { el.textContent = '99'; });
  assert.equal((await task('calendarState')).gridValid, false);
  await assert.rejects(() => task('pickDate', { value: '2026-09-30' }), /luoi ngay/);
  await tab.locator('.calendar-wrapper').evaluate(el => el.after(el.cloneNode(true)));
  await assert.rejects(() => task('pickDate', { value: '2026-09-30' }), /nhieu popup/);
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), []);
});

test('calendar navigates both ways over a year boundary and selects leap day', async () => {
  await mount({ shown: '2028-01-01', selected: '2028-01-01', minimum: '2027-01-01' });
  await task('openDate'); await expect(tab.locator('.calendar-wrapper')).toBeVisible();
  assert.equal(await task('changeMonth', { direction: -1 }), true);
  await expect.poll(async () => (await task('calendarState')).year).toBe(2027);
  assert.equal((await task('calendarState')).month, 12);
  await task('changeMonth', { direction: 1 });
  await expect.poll(async () => (await task('calendarState')).month).toBe(1);
  await task('changeMonth', { direction: 1 });
  await expect.poll(async () => (await task('calendarState')).month).toBe(2);
  assert.equal(await task('pickDate', { value: '2028-02-29' }), 'picked');
  assert.equal(await task('dateCheck', { date: '2028-02-29' }), true);
});

test('time wrapper stays open between hour and minute, missing minutes are not rounded', async () => {
  await mount(); await task('openTime'); await expect(tab.locator('.tiktok-timepicker-time-picker-container')).toBeVisible();
  await task('openTime');
  assert.equal(await tab.evaluate(() => window.opened.time), 1);
  assert.equal(await task('pickTime', { part: 'hour', value: '23' }), true);
  assert.equal(await task('pickTime', { part: 'minute', value: '03' }), false);
  assert.equal(await task('pickTime', { part: 'minute', value: '55' }), true);
  await expect(tab.locator('#time')).toHaveValue('23:55');
  await tab.locator('.tiktok-timepicker-time-picker-container').evaluate(el => el.after(el.cloneNode(true)));
  await assert.rejects(() => task('pickTime', { part: 'hour', value: '20' }), /nhieu popup/);
  assert.equal(await tab.evaluate(() => window.inputClicks), 0);
});

test('real extension waits for asynchronous wrappers and month changes, reopens minutes, then verifies before posting', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const priorMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() - 1, 1));
  await mount({ shown: priorMonth, selected: priorMonth, minimum: priorMonth, delay: 650, closeHour: true });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.equal(await task('scheduleCheck', { date: target, time: '20:15' }), true);
  assert.deepEqual(await tab.evaluate(() => window.navigation), [1]);
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), [target]);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 1, time: 2 });
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await tab.evaluate(() => window.inputClicks), 0);
});

test('real extension navigates backwards from the displayed month without advancing further', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const nextMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() + 1, 1));
  await mount({ shown: nextMonth, selected: nextMonth, minimum: target });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => window.navigation), [-1]);
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), [target]);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test('a month arrow that does not change the calendar stops without repeated clicks or posting', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const priorMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() - 1, 1));
  await mount({ shown: priorMonth, selected: priorMonth, minimum: priorMonth, stuck: true });
  const result = await message(job(target)); assert.equal(result.ok, false); assert.match(result.error, /chua chuyen dung thang/);
  assert.deepEqual(await tab.evaluate(() => window.navigation), [1]);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test('date readback mismatch stops before time selection and publishing', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow), selected = iso(new Date(Date.now() - 86400_000));
  await mount({ shown: target, selected, minimum: selected, ignoreDate: true });
  const result = await message(job(target)); assert.equal(result.ok, false); assert.match(result.error, /Ngay doc lai khong khop/);
  assert.equal(await tab.evaluate(() => window.opened.time), 0);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test('time readback mismatch stops before publishing', async () => {
  const target = iso(new Date(Date.now() + 86400_000));
  await mount({ shown: target, selected: target, minimum: target, ignoreTime: true });
  const result = await message(job(target)); assert.equal(result.ok, false); assert.match(result.error, /Gio doc lai khong khop/);
  assert.equal(await tab.evaluate(() => window.opened.date), 0);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test('already correct date and time never open or toggle either popup', async () => {
  const target = iso(new Date(Date.now() + 86400_000));
  await mount({ shown: target, selected: target, minimum: target });
  await tab.locator('#time').evaluate(el => { el.value = '20:15'; });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 0, time: 0 });
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test('captures the supplied popup fixtures for visual inspection', async () => {
  await mount({ original: true }); await task('openDate');
  await expect(tab.locator('.calendar-wrapper')).toBeVisible();
  await tab.locator('.tiktok-timepicker-time-picker-container').evaluate(el => { el.hidden = false; });
  await mkdir(path.join(root, 'test-results'), { recursive: true });
  await tab.screenshot({ path: path.join(root, 'test-results', 'schedule-pickers.png') });
});
