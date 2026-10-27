/* TikTok Studio from late October 2026: the schedule date and time are Picker boxes
   (<div class="Picker__root schedule-picker"><div role="combobox" aria-label="Select date" aria-expanded="false"
   data-open="false" class="Picker__trigger">…<span class="Picker__value">24 tháng 10, 2026</span></div></div>).
   Only the inner combobox takes the click; the wrapper does nothing. The popups may still be TikTok's
   calendar-wrapper / tiktok-timepicker, or new markup the extension has to read by its numbers. */
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
const job = date => ({ type: 'prepare', tabId, row: { id: 'picker', video, tieu_de: 'Test', hashtag: '', gio_dang: date + 'T20:15' }, schedule: true, publish: true });

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'omni-trigger-'));
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

// popup: 'classic' (TikTok's calendar-wrapper / tiktok-timepicker), 'generic' (unknown markup: a dialog with a
// heading, two arrows and day buttons; two columns of numbers) or 'unknown' (a popup holding no grid at all).
// open: 'click' (onclick on the trigger), 'pointer' (pointerdown only) or 'trusted' (real clicks only).
async function mount(options = {}) {
  const config = { shown: '2026-09-01', selected: '2026-09-30', minimum: '2026-09-30', time: '11:05', popup: 'classic', open: 'click', delay: 0, ...options };
  const svg = '<svg width="12" height="12"><path d="M0 0h12v12H0z"/></svg>';
  const trigger = (kind, icon) => `<div class="Picker__root schedule-picker" id="${kind}-root"><div id="${kind}-trigger" role="combobox" tabindex="0" aria-label="Select ${kind}" aria-haspopup="true" aria-expanded="false" data-open="false" data-form-control="" class="Picker__trigger Picker__trigger--variant-fill">
    <span class="Picker__leftIcon"><span role="img" class="px-icon " data-icon="${icon}" data-testid="${icon}">${svg}</span></span>
    <span class="Picker__value" id="${kind}-value"></span>
    <span role="img" class="px-icon Picker__indicator" data-icon="ArrowDown" data-testid="ArrowDown">${svg}</span></div></div>`;
  await tab.setContent(`<style>
    body { font:14px Arial; margin:24px; color:#222; }
    .scheduled-picker { display:flex; gap:16px; align-items:flex-start; } .Picker__trigger { border:1px solid #ccc; padding:8px; width:180px; cursor:pointer; display:flex; gap:6px; }
    .calendar-wrapper, .tiktok-timepicker-time-picker-container, .Picker__popover { position:static!important; border:1px solid #ccc; margin-top:12px; }
    .month-header-wrapper, .Picker__header { display:flex; justify-content:space-between; padding:12px; }
    .days-wrapper, .day-header-wrapper, .Picker__days, .Picker__weekdays { display:grid; grid-template-columns:repeat(7, 50px); text-align:center; }
    .day { display:inline-block; padding:8px; color:#999; } .day.valid { color:#222; } .day.selected { background:#eee; }
    .Picker__day { padding:6px; background:none; border:0; } .Picker__day[aria-disabled="true"] { color:#bbb; }
    .tiktok-timepicker-time-scroll-container { display:inline-block; width:70px; height:230px; overflow:auto; }
    .tiktok-timepicker-option-item { padding:6px; }
    .Picker__columns { display:flex; gap:12px; } .Picker__column { list-style:none; margin:0; padding:0; width:60px; height:200px; overflow:auto; } .Picker__option { padding:4px; }
  </style><input type="file" accept="video/mp4">
    <div class="jsx-77">Thời lượng: 38m41s · 2026-01-01</div>
    <div contenteditable="true" role="textbox" aria-label="Description" style="height:50px"></div>
    <div class="jsx-2816910013 scheduled-container new-form"><div class="jsx-2816910013 title-v2 scheduled-title-container"><span class="TUXText">Thời điểm đăng</span></div>
    <div class="jsx-2816910013 schedule-radio-container">
      <label class="Radio__root Radio__root--disabled-false"><span class="Radio__circle"><input type="radio" class="Radio__input" name="postSchedule" value="post_now"><span class="Radio__innerCircle Radio__innerCircle--checked-false"></span></span><span class="TUXText">Bây giờ</span></label>
      <label class="Radio__root Radio__root--disabled-false"><span class="Radio__circle"><input type="radio" class="Radio__input" name="postSchedule" value="schedule" checked><span class="Radio__innerCircle Radio__innerCircle--checked-true"></span></span><span class="TUXText">Lên lịch</span></label>
    </div>
    <div class="jsx-2816910013 scheduled-picker">${trigger('date', 'Calendar')}${trigger('time', 'Clock')}
      <div class="jsx-1574214355 timezone-select"><div class="Select__root"><button type="button" aria-expanded="false" aria-haspopup="dialog" role="combobox" data-open="false" data-form-control="" class="Select__trigger Select__trigger--variant-fill"><div class="Select__leftIcon">${svg}</div><div class="Select__triggerInner"><input role="input" type="text" placeholder="Tìm kiếm" class="Select__searchInput" value="(GMT+7) Giờ địa phương"></div><span role="img" class="px-icon Select__openIndicator" data-icon="ArrowDown">${svg}</span></button></div></div>
    </div></div>
    <div id="portal">${config.popup === 'classic' ? calendarHTML + timeHTML : ''}</div>
    <div class="info-progress success" style="width:100%;height:4px;visibility:visible"></div>
    <button id="publish" data-e2e="post_video_button">Lên lịch</button><div role="status" id="outcome"></div>`);
  await tab.evaluate(config => {
    const iso = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const vi = value => new Intl.DateTimeFormat('vi-VN', { dateStyle: 'long' }).format(new Date(value + 'T12:00'));
    const dateValue = document.querySelector('#date-value'), timeValue = document.querySelector('#time-value');
    const state = { date: config.selected, time: config.time };
    dateValue.textContent = vi(state.date); timeValue.textContent = state.time;
    window.clicks = 0; window.navigation = []; window.chosenDates = []; window.opened = { date: 0, time: 0 }; window.ignored = 0; window.wrapperClicks = 0;
    let shown = new Date(config.shown + 'T12:00');
    const portal = document.querySelector('#portal'), popups = { date: null, time: null };
    const setOpen = (kind, open) => {
      const trigger = document.querySelector(`#${kind}-trigger`);
      trigger.setAttribute('aria-expanded', String(open)); trigger.setAttribute('data-open', String(open));
      if (popups[kind]) popups[kind].hidden = !open;
    };
    const chooseDate = (value, allowed) => {
      window.chosenDates.push(value);
      if (!allowed) return;
      state.date = value; dateValue.textContent = vi(value); setOpen('date', false);
    };
    const chooseTime = (hour, text) => setTimeout(() => {
      const parts = state.time.split(':'); parts[hour ? 0 : 1] = text;
      state.time = parts.join(':'); timeValue.textContent = state.time;
      if (hour) setOpen('time', false);
    }, config.delay);
    if (config.popup === 'classic') {
      popups.date = document.querySelector('.calendar-wrapper'); popups.time = document.querySelector('.tiktok-timepicker-time-picker-container');
      const months = ['Tháng Một', 'Tháng Hai', 'Tháng Ba', 'Tháng Tư', 'Tháng Năm', 'Tháng Sáu', 'Tháng Bảy', 'Tháng Tám', 'Tháng Chín', 'Tháng Mười', 'Tháng Mười Một', 'Tháng Mười Hai'];
      const render = () => {
        popups.date.querySelector('.month-title').textContent = months[shown.getMonth()];
        popups.date.querySelector('.year-title').textContent = shown.getFullYear();
        popups.date.querySelectorAll('.days-wrapper').forEach(row => row.remove());
        const year = shown.getFullYear(), month = shown.getMonth(), offset = new Date(year, month, 1).getDay();
        const count = Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7;
        for (let i = 0; i < count; i += 7) {
          const row = document.createElement('div'); row.className = 'jsx-1793871833 days-wrapper';
          for (let j = 0; j < 7; j++) {
            const day = new Date(year, month, 1 - offset + i + j), value = iso(day);
            const container = document.createElement('div'); container.className = 'jsx-1793871833 day-span-container';
            const cell = document.createElement('span'); cell.className = 'jsx-1793871833 day'; cell.textContent = day.getDate();
            if (value >= config.minimum) cell.classList.add('valid');
            if (value === state.date) cell.classList.add('selected');
            cell.onclick = () => chooseDate(value, cell.classList.contains('valid'));
            container.append(cell); row.append(container);
          }
          popups.date.append(row);
        }
      };
      render();
      popups.date.querySelectorAll('.arrow').forEach((arrow, i) => {
        arrow.onclick = () => {
          const direction = i ? 1 : -1; window.navigation.push(direction);
          setTimeout(() => { shown = new Date(shown.getFullYear(), shown.getMonth() + direction, 1); render(); }, config.delay);
        };
      });
      for (const span of popups.time.querySelectorAll('.tiktok-timepicker-option-text')) span.onclick = () => chooseTime(span.classList.contains('tiktok-timepicker-left'), span.textContent);
    } else if (config.popup === 'generic') {
      popups.date = document.createElement('div'); popups.date.className = 'Picker__popover'; popups.date.setAttribute('role', 'dialog');
      popups.time = document.createElement('div'); popups.time.className = 'Picker__popover Picker__popover--time'; popups.time.setAttribute('role', 'dialog');
      portal.append(popups.date, popups.time);
      const render = () => {
        const year = shown.getFullYear(), month = shown.getMonth(), offset = new Date(year, month, 1).getDay();
        const count = Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7;
        const icon = name => `<span role="img" class="px-icon" data-icon="${name}"><svg width="8" height="8"><path d="M0 0h8v8H0z"/></svg></span>`;
        let html = `<div class="Picker__header"><button type="button" class="Picker__nav" data-dir="-1">${icon('ArrowLeft')}</button><span class="Picker__title">Tháng ${month + 1}, ${year}</span>` +
          `<button type="button" class="Picker__nav" data-dir="1" aria-label="Tháng sau">${icon('ArrowRight')}</button></div>` +
          `<div class="Picker__weekdays">${['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'].map(name => `<span>${name}</span>`).join('')}</div><div class="Picker__days">`;
        for (let i = 0; i < count; i++) {
          const day = new Date(year, month, 1 - offset + i), value = iso(day), outside = day.getMonth() !== month;
          html += `<button type="button" class="Picker__day${outside ? ' Picker__day--outside' : ''}" data-value="${value}"${outside || value < config.minimum ? ' aria-disabled="true"' : ''}><span>${day.getDate()}</span></button>`;
        }
        popups.date.innerHTML = html + '</div>';
        popups.date.querySelectorAll('.Picker__nav').forEach(button => {
          button.onclick = () => {
            const direction = Number(button.dataset.dir); window.navigation.push(direction);
            setTimeout(() => { shown = new Date(shown.getFullYear(), shown.getMonth() + direction, 1); render(); }, config.delay);
          };
        });
        popups.date.querySelectorAll('.Picker__day').forEach(button => { button.onclick = () => chooseDate(button.dataset.value, button.getAttribute('aria-disabled') !== 'true'); });
      };
      render();
      const column = (count, part) => `<ul class="Picker__column" data-part="${part}">${Array.from({ length: count }, (_, i) => `<li class="Picker__option"><span>${String(i).padStart(2, '0')}</span></li>`).join('')}</ul>`;
      popups.time.innerHTML = `<div class="Picker__columns">${column(24, 'hour')}${column(60, 'minute')}</div>`;
      popups.time.querySelectorAll('.Picker__option').forEach(option => { option.onclick = () => chooseTime(option.closest('ul').dataset.part === 'hour', option.textContent.trim()); });
    } else {
      popups.date = document.createElement('div'); popups.date.className = 'Picker__popover'; popups.date.setAttribute('role', 'dialog');
      popups.date.innerHTML = '<p class="Picker__empty">Chọn ngày đăng</p>';
      portal.append(popups.date);
    }
    for (const kind of ['date', 'time']) if (popups[kind]) popups[kind].hidden = true;
    window.dismissed = 0;
    const dismiss = (kind, event) => {
      const trigger = document.querySelector(`#${kind}-trigger`);
      if (!popups[kind] || popups[kind].hidden || popups[kind].contains(event.target) || trigger.contains(event.target)) return;
      window.dismissed++; setOpen(kind, false);
    };
    document.addEventListener('pointerdown', event => { for (const kind of ['date', 'time']) dismiss(kind, event); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') for (const kind of ['date', 'time']) if (popups[kind] && !popups[kind].hidden) { window.dismissed++; setOpen(kind, false); } });
    const toggle = kind => {
      window.opened[kind]++;
      setTimeout(() => {
        const open = document.querySelector(`#${kind}-trigger`).getAttribute('aria-expanded') !== 'true';
        setOpen(kind, open);
        if (open) setOpen(kind === 'date' ? 'time' : 'date', false);
      }, config.delay);
    };
    for (const kind of ['date', 'time']) {
      const trigger = document.querySelector(`#${kind}-trigger`), root = document.querySelector(`#${kind}-root`);
      root.addEventListener('click', event => { if (event.target === root) window.wrapperClicks++; });
      if (config.open === 'pointer') trigger.addEventListener('pointerdown', () => toggle(kind));
      else trigger.addEventListener('click', event => { if (config.open === 'trusted' && !event.isTrusted) { window.ignored++; return; } toggle(kind); });
    }
    document.querySelector('#publish').onclick = () => { window.clicks++; document.querySelector('#outcome').textContent = 'Video has been scheduled'; };
  }, config);
}

test('Picker triggers are the schedule fields; the click goes to the combobox, not its wrapper', async () => {
  await mount();
  assert.equal(await task('schedule'), 'already');
  assert.equal(await task('scheduleReady'), true);
  const state = await task('scheduleSnapshot');
  assert.equal(state.date.value, '30 tháng 9, 2026'); assert.equal(state.date.readonly, true); assert.equal(state.date.expanded, false);
  assert.match(state.date.class, /Picker__trigger/);
  assert.equal(state.time.value, '11:05'); assert.equal(state.time.expanded, false);
  assert.equal(await task('dateCheck', { date: '2026-09-30' }), true);
  assert.equal(await task('dateCheck', { date: '2026-01-01' }), false);
  assert.equal(await task('timeCheck', { time: '11:05' }), true);
  assert.equal(await task('scheduleCheck', { date: '2026-09-30', time: '11:05' }), true);
  assert.equal(await task('datePickerReady', { date: '2026-09-30' }), false);
  assert.equal(await task('openDate', { date: '2026-09-30' }), true);
  await expect(tab.locator('.calendar-wrapper')).toBeVisible();
  assert.equal(await tab.evaluate(() => window.opened.date), 1);
  assert.equal(await task('pickerExpanded', { field: 'date' }), true);
  assert.equal((await task('scheduleSnapshot')).date.expanded, true);
  assert.equal(await task('openDate', { date: '2026-09-30' }), true, 'an open popup is not toggled again');
  assert.equal(await tab.evaluate(() => window.opened.date), 1);
  const inspected = await task('inspect');
  assert.match(inspected.scheduleHtml, /Select date/);
  assert.match(inspected.popupHtml, /calendar-wrapper/);
  assert.doesNotMatch(inspected.popupHtml, /Picker__trigger|<path/);
  const rect = await task('fieldRect', { field: 'time' });
  const box = await tab.locator('#time-trigger').boundingBox();
  assert.ok(rect.x > box.x && rect.x < box.x + box.width && rect.y > box.y && rect.y < box.y + box.height);
});

test('real extension schedules through Picker triggers with the known popups', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const priorMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() - 1, 1));
  await mount({ shown: priorMonth, selected: priorMonth, minimum: priorMonth, delay: 300 });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.equal(await task('scheduleCheck', { date: target, time: '20:15' }), true);
  assert.equal(await tab.locator('#time-value').innerText(), '20:15');
  assert.deepEqual(await tab.evaluate(() => window.navigation), [1]);
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), [target]);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 1, time: 2 });
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test('unknown popups are read by their numbers: a day grid under a heading, hour and minute columns', async () => {
  const tomorrow = new Date(Date.now() + 86400_000), target = iso(tomorrow);
  const priorMonth = iso(new Date(tomorrow.getFullYear(), tomorrow.getMonth() - 1, 1));
  await mount({ popup: 'generic', open: 'pointer', shown: priorMonth, selected: priorMonth, minimum: priorMonth, delay: 200 });
  assert.equal(await task('datePickerReady', { date: target }), false);
  assert.equal(await task('timePickerReady'), false);
  // A plain click does nothing to this component; pointer events open it.
  await task('openDate', { date: target });
  await tab.waitForTimeout(400);
  assert.equal(await task('datePickerReady', { date: target }), false);
  await task('openDate', { date: target, strategy: 'events' });
  await expect(tab.locator('.Picker__popover[role="dialog"]').first()).toBeVisible();
  // An open picker popover is not a dialog that blocks the caption or the publish button.
  assert.equal((await task('publishOutcome')).state, 'waiting');
  assert.equal((await task('captionSnapshot')).dialogOpen, false);
  assert.equal(await task('pickersClosed'), false);
  const calendar = await task('calendarState');
  assert.equal(calendar.count, 1); assert.equal(calendar.generic, true); assert.equal(calendar.gridValid, true);
  assert.equal(calendar.index, Number(priorMonth.slice(0, 4)) * 12 + Number(priorMonth.slice(5, 7)) - 1);
  assert.equal(await task('pickDate', { value: target }), 'missing', 'the target month is not shown yet');
  assert.match((await task('inspect')).popupHtml, /Picker__days/);
  // A fresh page for the real run: the dialog left open above would stop the caption step.
  await mount({ popup: 'generic', open: 'pointer', shown: priorMonth, selected: priorMonth, minimum: priorMonth, delay: 200 });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.equal(await task('scheduleCheck', { date: target, time: '20:15' }), true);
  assert.deepEqual(await tab.evaluate(() => window.navigation), [1]);
  assert.deepEqual(await tab.evaluate(() => window.chosenDates), [target]);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 1, time: 2 });
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await tab.evaluate(() => window.wrapperClicks), 0);
  // The time popover left open after the minute was dismissed before Lên lịch, not toggled by its trigger.
  assert.equal(await tab.locator('#time-trigger').getAttribute('aria-expanded'), 'false');
  assert.ok(await tab.evaluate(() => window.dismissed) >= 1);
  assert.equal(await task('pickersClosed'), true);
});

test('a trigger that answers real clicks only is opened through the debugger', async () => {
  const target = iso(new Date(Date.now() + 86400_000));
  await mount({ open: 'trusted', shown: target, selected: target, minimum: target, time: '09:00' });
  const result = await message(job(target)); assert.equal(result.ok, true, result.error);
  assert.equal(await task('scheduleCheck', { date: target, time: '20:15' }), true);
  assert.deepEqual(await tab.evaluate(() => window.opened), { date: 0, time: 2 });
  assert.ok(await tab.evaluate(() => window.ignored) >= 2, 'synthetic clicks were tried first and ignored by the page');
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test('a popup that opens but holds nothing readable stops with its markup in the diagnostic', async () => {
  const target = iso(new Date(Date.now() + 86400_000));
  await mount({ popup: 'unknown' });
  const failed = await message(job(target));
  assert.equal(failed.ok, false);
  assert.match(failed.error, /Popup ngay da mo \(aria-expanded\) nhung chua nhan dien duoc/);
  assert.equal(await tab.evaluate(() => window.opened.date), 1, 'no further clicks on a box that reports itself open');
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  const { lastDiagnostic } = await dashboard.evaluate(() => chrome.storage.local.get('lastDiagnostic'));
  assert.equal(lastDiagnostic.frames[0].schedule.date.expanded, true);
  assert.match(lastDiagnostic.frames[0].popupHtml, /Picker__empty/);
  assert.match(lastDiagnostic.frames[0].scheduleHtml, /Picker__trigger/);
});
