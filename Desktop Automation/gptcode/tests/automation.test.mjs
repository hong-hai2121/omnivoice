import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { chromium, expect } from "@playwright/test";
import { mkdtemp, writeFile, rm, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pageTask } from "../extension/dom.js";
import { episodeKey } from "../extension/model.js";

const root = fileURLToPath(new URL("../", import.meta.url));
let context, directory, dashboard, tab, tabId, video, body, extensionId;
const date = new Date(Date.now() + 86400_000).toLocaleDateString("en-CA");
const editor = `<div contenteditable="true" role="textbox" aria-label="Description" style="width:260px;height:80px"></div>`;
const fixture = `<input type="file" accept="video/mp4">${editor}
  <label><input type="checkbox" checked id="schedule">Schedule</label>
  <input type="date" aria-label="Date"><input type="time" aria-label="Time">
  <button id="publish">Schedule</button><div role="status" id="outcome"></div>
  <div class="info-progress success" style="height:4px;width:100%;visibility:visible"></div>
  <script>window.clicks=0; document.querySelector('#publish').onclick=()=>{
    window.clicks++; document.querySelector('#outcome').textContent='Video has been scheduled';
  };</script>`;
const task = (action, data = {}) => tab.evaluate(`(${pageTask.toString()})(${JSON.stringify(action)},${JSON.stringify(data)})`);
const message = request => dashboard.evaluate(request => chrome.runtime.sendMessage(request), request);
const job = (overrides = {}) => ({ type: "prepare", tabId, row: { id: "a", video, tieu_de: "Test", hashtag: "", gio_dang: date + "T20:00" }, schedule: true, ...overrides });

async function copyrightDialog(options = {}) {
  await tab.evaluate(({ disabled = false, unknownAfter = false, copyright = true }) => {
    window.confirmClicks = 0;
    document.querySelector('#publish').onclick = () => {
      window.clicks++;
      const modal = document.createElement('div'); modal.setAttribute('role', 'dialog');
      modal.innerHTML = `<h2>Tiếp tục đăng?</h2>${copyright ? '<p>Kiểm tra bản quyền chưa hoàn tất. Nếu bạn đăng video bây giờ thì quá trình kiểm tra sẽ chấm dứt.</p>' : ''}
        <p>Chúng tôi vẫn đang kiểm tra video của bạn để phát hiện xem có vấn đề tiềm ẩn hay không. Bạn có muốn tiếp tục đăng trước khi quy trình kiểm tra hoàn tất không?</p>
        <button type="button" class="TUXButton TUXButton--secondary">Hủy</button>
        <button id="confirm-post" class="TUXButton TUXButton--default TUXButton--medium TUXButton--primary" aria-disabled="false" type="button"><div class="TUXButton-content"><div class="TUXButton-label">Đăng ngay</div></div></button>`;
      document.body.append(modal);
      const confirm = modal.querySelector('#confirm-post'); confirm.disabled = disabled;
      confirm.onclick = () => {
        window.confirmClicks++;
        if (unknownAfter) modal.innerHTML = '<h2>Confirm account</h2>';
        else { modal.remove(); document.querySelector('#outcome').textContent = document.querySelector('#schedule').checked ? 'Video has been scheduled' : 'Video has been posted'; }
      };
    };
  }, options);
}

async function pendingCopyrightConfirmation(options = {}) {
  const prepared = await message(job()); assert.equal(prepared.ok, true, prepared.error);
  await copyrightDialog(options);
  await tab.locator('#publish').click();
  const request = job({ type: 'fill', publish: true });
  await dashboard.evaluate(({ key, row }) => chrome.storage.local.set({ submissions: {
    [key]: { state: 'uncertain', video: row.video, date: row.gio_dang, at: new Date().toISOString() },
  } }), { key: episodeKey(video), row: request.row });
  return request;
}

async function replaceCaptionWhileTyping(options = {}) {
  await tab.evaluate(({ mode = 'node', repeat = false, foreignFocus = false, invalidateDraft = false, dialog = false }) => {
    window.replacements = 0; window.enterTags = [];
    const bind = editor => {
      if (mode === 'key') editor.setAttribute('data-editor', 'editor-' + window.replacements);
      let pending = false;
      editor.oninput = () => {
        if (pending || !editor.innerText.includes('#first') || (!repeat && window.replacements)) return;
        pending = true;
        setTimeout(() => {
          window.replacements++;
          const next = mode === 'node' ? editor.cloneNode(false) : editor;
          if (mode === 'node') editor.replaceWith(next); else editor.blur();
          next.textContent = '[Full] fixture'; bind(next);
          if (invalidateDraft) document.querySelector('[type="file"]').dispatchEvent(new Event('change'));
          if (foreignFocus) document.querySelector('#publish').focus();
          if (dialog) document.body.insertAdjacentHTML('beforeend', '<div role="dialog">Confirm</div>');
        }, 150);
      };
      editor.onkeydown = event => {
        if (event.key === 'Enter') { event.preventDefault(); window.enterTags.push(editor.innerText.match(/#\w+$/)?.[0]); }
      };
    };
    bind(document.querySelector('[role="textbox"]'));
  }, options);
}

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "omni-automation-"));
  video = path.join(directory, "fixture.mp4");
  await writeFile(video, "test bytes");
  const extension = path.join(root, "extension");
  context = await chromium.launchPersistentContext(path.join(directory, "profile"), {
    headless: true, channel: "chromium", args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  extensionId = new URL(worker.url()).host;
  await context.route("https://www.tiktok.com/**", route => route.fulfill({ contentType: "text/html", body }));
  await context.route("http://127.0.0.1:8771/**", route => route.fulfill({ contentType: "application/json", body: '{"ok":true,"muc":[]}' }));
  body = fixture;
  tab = await context.newPage(); await tab.goto("https://www.tiktok.com/tiktokstudio/upload");
  dashboard = await context.newPage(); await dashboard.goto(`chrome-extension://${extensionId}/dashboard.html`);
  await dashboard.locator("#tab option").waitFor({ state: "attached" });
  tabId = Number(await dashboard.locator("#tab").inputValue());
});
beforeEach(async () => {
  await dashboard.evaluate(() => chrome.storage.local.remove(["submissions", "rowResults", "progress"]));
  body = fixture; await tab.goto("https://www.tiktok.com/tiktokstudio/upload");
});
after(async () => {
  await context?.close();
  if (directory) await rm(directory, { recursive: true, force: true });
});

test("waits for a delayed video input in an iframe and ignores thumbnail inputs", async () => {
  await tab.setContent('<input type="file" accept="image/*"><iframe id="frame"></iframe>');
  const frame = tab.frames()[1];
  await frame.setContent(editor + `<input type="file" accept="image/*"><script>
    setTimeout(()=>{const f=document.createElement('input'); f.type='file'; f.accept='.MP4'; document.body.append(f)},700);
    </script>`);
  const result = await message(job({ schedule: false }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await frame.locator('input[accept=".MP4"]').evaluate(el => el.files[0].name), "fixture.mp4");
  assert.equal(await frame.locator('[role="textbox"]').innerText(), "Test");
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files.length), 0);
});

test("finds upload and editor in open shadow DOM", async () => {
  await tab.setContent('<div id="host"></div>');
  await tab.evaluate(html => { document.querySelector('#host').attachShadow({ mode: 'open' }).innerHTML = html; }, fixture);
  const result = await message(job({ schedule: false }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files.length), 1);
  assert.equal(await task("captionCheck", { text: "Test" }), true);
});

test("opens a lazy upload control without a native file dialog", async () => {
  await tab.setContent(editor + `<button id="select">Select video</button><script>
    document.querySelector('#select').onclick=()=>{const f=document.createElement('input');f.type='file';f.accept='video/*';document.body.append(f);f.click()};
    </script>`);
  const result = await message(job({ schedule: false }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files.length), 1);
});

test("file verification survives a site clearing the input after receiving the file", async () => {
  await tab.evaluate(() => {
    document.querySelector('input[type=file]').addEventListener('change', event => {
      window.receivedFile = event.target.files[0].name;
      event.target.value = '';
      event.target.remove();
    });
  });
  const result = await message(job({ schedule: false }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.receivedFile), 'fixture.mp4');
  assert.equal(await task('captionCheck', { text: 'Test' }), true);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test("missing and empty files fail verification without publishing", async () => {
  const empty = path.join(directory, 'empty.mp4'); await writeFile(empty, '');
  for (const candidate of [path.join(directory, 'missing.mp4'), empty]) {
    await tab.reload();
    const request = job({ schedule: false }); request.row.video = candidate;
    const result = await message(request);
    assert.equal(result.ok, false); assert.match(result.error, /Chrome không đọc được nội dung video/);
    assert.ok(result.error.includes(candidate));
    assert.equal(await tab.evaluate(() => window.clicks), 0);
  }
});

test("ambiguous upload fields fail and save frame diagnostics", async () => {
  await tab.setContent('<input type="file" accept="video/*"><input type="file" accept="video/*">');
  const result = await message(job({ schedule: false }));
  assert.equal(result.ok, false);
  assert.match(result.error, /2/);
  const diagnostic = await dashboard.evaluate(async () => (await chrome.storage.local.get("lastDiagnostic")).lastDiagnostic);
  assert.equal(diagnostic.frames[0].controls.length, 2);
});

test("adds a space before every hashtag, waits one second, then sends a trusted Enter", async () => {
  await tab.evaluate(() => {
    window.tags = []; window.enters = [];
    const caption = document.querySelector('[role="textbox"]');
    let lastInput = 0;
    caption.addEventListener('input', () => { lastInput = performance.now(); });
    caption.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      window.tags.push(caption.innerText.match(/#\w+$/)?.[0]);
      window.enters.push({ waited: performance.now() - lastInput, trusted: event.isTrusted, text: caption.innerText });
    });
  });
  const request = job({ schedule: false }); request.row.hashtag = '#first #second';
  const result = await message(request);
  assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => window.tags), ['#first', '#second']);
  const enters = await tab.evaluate(() => window.enters);
  assert.ok(enters.every(event => event.waited >= 1000 && event.trusted));
  assert.equal(enters[0].text, 'Test #first');
  assert.equal(enters[1].text, 'Test #first #second');
  assert.equal(await task("captionCheck", { text: 'Test\n#first #second' }), true);
});

test("Enter is not sent when focus moves from the caption to a publish button", async () => {
  await tab.evaluate(() => document.querySelector('[role="textbox"]').addEventListener('input', event => {
    if (event.target.innerText.includes('#first')) document.querySelector('#publish').focus();
  }));
  const request = job({ schedule: false }); request.row.hashtag = '#first';
  const result = await message(request);
  assert.equal(result.ok, false); assert.match(result.error, /mất focus/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test('caption replacement while waiting for Enter is retried once on the same draft', async () => {
  await replaceCaptionWhileTyping();
  const request = job({ publish: true }); request.row.hashtag = '#first #second';
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.replacements), 1);
  assert.deepEqual(await tab.evaluate(() => window.enterTags), ['#first', '#second']);
  assert.equal(await task('captionCheck', { text: 'Test #first #second' }), true);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test('a changed Draft editor key on the same element also triggers bounded recovery', async () => {
  await replaceCaptionWhileTyping({ mode: 'key' });
  const request = job(); request.row.hashtag = '#first #second';
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.equal(await task('captionCheck', { text: 'Test #first #second' }), true);
  assert.deepEqual(await tab.evaluate(() => window.enterTags), ['#first', '#second']);
});

test('continuous caption replacement stops after one retry without Enter or publication', async () => {
  await replaceCaptionWhileTyping({ repeat: true });
  const request = job({ publish: true }); request.row.hashtag = '#first';
  const result = await message(request); assert.equal(result.ok, false);
  assert.equal(await tab.evaluate(() => window.replacements), 2);
  assert.deepEqual(await tab.evaluate(() => window.enterTags), []);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test('replacement never steals focus from publish or bypasses a modal', async () => {
  for (const options of [{ foreignFocus: true }, { dialog: true }]) {
    await tab.reload(); await replaceCaptionWhileTyping(options);
    const request = job({ publish: true }); request.row.hashtag = '#first';
    const result = await message(request); assert.equal(result.ok, false);
    assert.equal(await tab.evaluate(() => window.replacements), 1);
    assert.deepEqual(await tab.evaluate(() => window.enterTags), []);
    assert.equal(await tab.evaluate(() => window.clicks), 0);
  }
});

test('replacement recovery cannot continue after the draft file changes', async () => {
  await replaceCaptionWhileTyping({ invalidateDraft: true });
  const request = job({ publish: true }); request.row.hashtag = '#first';
  const result = await message(request); assert.equal(result.ok, false);
  assert.equal(await tab.evaluate(() => window.replacements), 1);
  assert.deepEqual(await tab.evaluate(() => window.enterTags), []);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test('caption initialization settles before the first title is entered', async () => {
  await tab.evaluate(() => {
    document.querySelector('[type="file"]').addEventListener('change', () => {
      setTimeout(() => {
        const editor = document.querySelector('[role="textbox"]');
        const next = editor.cloneNode(false); next.textContent = 'File name'; editor.replaceWith(next);
        next.oninput = () => { window.firstInputAt ||= performance.now(); };
        setTimeout(() => { next.textContent = 'Final file name'; window.readyAt = performance.now(); }, 300);
      }, 100);
    }, { once: true });
  });
  const result = await message(job({ schedule: false })); assert.equal(result.ok, true, result.error);
  assert.equal(await task('captionCheck', { text: 'Test' }), true);
  assert.ok(await tab.evaluate(() => window.firstInputAt - window.readyAt >= 1000));
});

test('caption snapshots track identity, Draft key and focus separately from text', async () => {
  await tab.locator('[role="textbox"]').evaluate(el => { el.innerHTML = '<div data-editor="old">Initial</div>'; });
  await task('captionFocusOnly');
  const first = await task('captionSnapshot');
  assert.equal(first.focused, true); assert.equal(first.editorKey, 'old');
  await tab.locator('[data-editor]').evaluate(el => { el.textContent = 'Edited'; });
  const edited = await task('captionSnapshot');
  assert.equal(first.editorId, edited.editorId); assert.equal(first.editorKey, edited.editorKey);
  await tab.locator('[data-editor]').evaluate(el => el.setAttribute('data-editor', 'new'));
  const reset = await task('captionSnapshot');
  assert.equal(reset.editorId, first.editorId); assert.equal(reset.editorKey, 'new');
  await tab.locator('[role="textbox"]').evaluate(el => el.replaceWith(el.cloneNode(true)));
  const replaced = await task('captionSnapshot');
  assert.notEqual(replaced.editorId, reset.editorId); assert.equal(replaced.focused, false);
});

test('stop during caption recovery cancels before any retry input or publish', async () => {
  await replaceCaptionWhileTyping();
  const request = job({ publish: true }); request.row.hashtag = '#first';
  const running = message(request);
  try {
    await expect.poll(() => dashboard.evaluate(async () => {
      const { progress } = await chrome.storage.local.get('progress');
      return progress?.log.some(line => line.includes('Chờ ổn định rồi điền lại'));
    }), { timeout: 10_000, intervals: [50] }).toBe(true);
    await message({ type: 'stop' });
    const result = await running; assert.equal(result.ok, false); assert.match(result.error, /Da dung/);
    assert.deepEqual(await tab.evaluate(() => window.enterTags), []);
    assert.equal(await tab.locator('[role="textbox"]').innerText(), '[Full] fixture');
    assert.equal(await tab.evaluate(() => window.clicks), 0);
  } finally { await message({ type: 'stop' }); await running; }
});

test("native caret movement preserves previously committed noneditable hashtag tokens", async () => {
  await tab.evaluate(() => {
    const editor = document.querySelector('[role="textbox"]');
    window.nativeEnds = 0;
    editor.addEventListener('keydown', event => {
      if (event.ctrlKey && event.key === 'End') window.nativeEnds++;
      if (event.key !== 'Enter') return;
      event.preventDefault();
      const text = editor.innerText, tags = text.match(/#\w+/g) || [];
      editor.replaceChildren(document.createTextNode('Test '));
      for (const tag of tags) {
        const token = document.createElement('span'); token.contentEditable = 'false'; token.textContent = tag;
        editor.append(token, document.createTextNode(' '));
      }
      const token = editor.querySelector('span:last-of-type');
      const range = document.createRange(); range.selectNode(token);
      getSelection().removeAllRanges(); getSelection().addRange(range);
    });
  });
  const request = job({ schedule: false }); request.row.hashtag = '#episode123 #audio #fyp';
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.nativeEnds), 3);
  assert.deepEqual(await tab.locator('[role="textbox"] span').allTextContents(), ['#episode123', '#audio', '#fyp']);
});

test("a lost hashtag gets one repair pass before advancing to the next hashtag", async () => {
  await tab.evaluate(() => {
    window.enterCount = 0;
    const editor = document.querySelector('[role="textbox"]');
    editor.onkeydown = event => {
      if (event.key !== 'Enter') return;
      event.preventDefault(); window.enterCount++;
      if (window.enterCount === 1) editor.textContent = 'Test';
    };
  });
  const request = job({ schedule: false }); request.row.hashtag = '#first #second';
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.enterCount), 3);
  assert.equal(await task('captionCheck', { text: 'Test #first #second' }), true);
});

test("title mismatch warns but still schedules and publishes when both options are selected", async () => {
  await tab.evaluate(() => {
    const editor = document.querySelector('[role="textbox"]');
    editor.addEventListener('input', () => { if (editor.textContent === 'Test') editor.textContent = 'Changed title'; });
  });
  const result = await message(job({ publish: true }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  const progress = await dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress);
  assert.equal(progress.status, 'done');
  assert.ok(progress.log.some(line => line.includes('Cảnh báo: tiêu đề')));
});

test("title mismatch still stops preparation without both options, and diagnostics include the actual caption", async () => {
  await tab.evaluate(() => {
    const editor = document.querySelector('[role="textbox"]');
    editor.addEventListener('input', () => { editor.textContent = 'Changed title'; });
  });
  const result = await message(job()); assert.equal(result.ok, false);
  assert.match(result.error, /Tiêu đề chưa khớp/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  const diagnostic = await dashboard.evaluate(async () => (await chrome.storage.local.get('lastDiagnostic')).lastDiagnostic);
  assert.equal(diagnostic.expectedCaption.title, 'Test');
  assert.equal(diagnostic.captionTrace.at(-1).text, 'Changed title');
  assert.equal(diagnostic.frames[0].caption.text, 'Changed title');
  assert.match(diagnostic.screenshot, /^data:image\/png;base64,/);
});

test("lost hashtags remain a hard stop even when scheduling and publishing are checked", async () => {
  await tab.evaluate(() => {
    const editor = document.querySelector('[role="textbox"]');
    editor.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); editor.textContent = 'Test'; } };
  });
  const request = job({ publish: true }); request.row.hashtag = '#first';
  const result = await message(request); assert.equal(result.ok, false);
  assert.match(result.error, /hashtag chưa được giữ đủ/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test("the supplied TikTok radio and time columns work, and publishing waits for success at 100 percent", async () => {
  const column = (side, values) => `<div class="tiktok-timepicker-time-scroll-container tiktok-timepicker-disable-scrollbar"><div class="tiktok-timepicker-option-list">${values.map(value => `<div class="tiktok-timepicker-option-item"><span class="tiktok-timepicker-option-text tiktok-timepicker-${side}">${String(value).padStart(2, '0')}</span></div>`).join('')}</div></div>`;
  await tab.setContent(`<input type="file" accept="video/mp4">${editor}
    <style>.Radio__innerCircle { display:inline-block;width:16px;height:16px; }</style>
    <div class="Radio__root"><span class="Radio__innerCircle Radio__innerCircle--checked-true"></span>Now</div>
    <div id="radio" class="Radio__root"><span class="Radio__innerCircle Radio__innerCircle--checked-false"></span>Lên lịch</div>
    <div class="scheduled-picker" hidden><input class="TUXTextInputCore-input" readonly value="22:20">
      <div class="tiktok-timepicker-time-picker-container" hidden>${column('left', Array.from({length:24}, (_,i)=>i))}${column('right', Array.from({length:12}, (_,i)=>i*5))}</div>
      <input class="TUXTextInputCore-input" readonly value="${date}"></div>
    <button id="publish" role="button" type="button" class="Button__root" data-e2e="post_video_button" aria-disabled="false" data-loading="false" data-disabled="false"><div class="Button__content">Lên lịch</div></button>
    <div class="info-progress" style="height:4px;width:90%;visibility:visible"></div><div role="status" id="outcome"></div>`);
  await tab.evaluate(() => {
    window.clicks = 0; window.sequence = []; window.dateClicks = 0;
    const [timeInput, dateInput] = document.querySelectorAll('.scheduled-picker input');
    const picker = document.querySelector('.tiktok-timepicker-time-picker-container');
    dateInput.onclick = () => window.dateClicks++;
    timeInput.onclick = () => { picker.hidden = false; };
    document.querySelector('#radio').onclick = () => {
      window.sequence.push('schedule');
      document.querySelector('#radio span').className = 'Radio__innerCircle Radio__innerCircle--checked-true';
      document.querySelector('.scheduled-picker').hidden = false;
    };
    document.querySelector('[role="textbox"]').onkeydown = event => {
      if (event.key === 'Enter') { event.preventDefault(); window.sequence.push('hashtag'); }
    };
    for (const option of picker.querySelectorAll('.tiktok-timepicker-option-item')) option.onclick = () => {
      const span = option.querySelector('span'), [hour, minute] = timeInput.value.split(':');
      const isHour = span.classList.contains('tiktok-timepicker-left');
      timeInput.value = isHour ? span.textContent + ':' + minute : hour + ':' + span.textContent;
      window.sequence.push(isHour ? 'hour' : 'minute');
    };
    document.querySelector('#publish').onclick = () => { window.clicks++; window.sequence.push('publish'); document.querySelector('#outcome').textContent = 'Video has been scheduled'; };
  });
  const request = job({ publish: true }); request.row.id = 'tiktok-dom'; request.row.hashtag = '#one #two';
  const running = message(request);
  await expect.poll(() => dashboard.evaluate(async () => {
    const { progress } = await chrome.storage.local.get('progress');
    return progress?.rowId === 'tiktok-dom' && progress.status === 'running' && progress.log.at(-1).includes('Dang cho tai/xu ly');
  }), { timeout: 15_000 }).toBe(true);
  assert.deepEqual(await tab.evaluate(() => window.sequence), ['hashtag', 'hashtag', 'schedule', 'hour', 'minute']);
  assert.equal(await tab.evaluate(() => window.dateClicks), 0);
  await tab.locator('.info-progress').evaluate(el => { el.style.width = '100%'; });
  await tab.waitForTimeout(650);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  await tab.locator('.info-progress').evaluate(el => el.classList.add('success'));
  const result = await running; assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await task('scheduleCheck', { date, time: '20:00' }), true);
  const sequence = await tab.evaluate(() => window.sequence);
  assert.equal(await task('schedule'), 'already');
  assert.deepEqual(await tab.evaluate(() => window.sequence), sequence);
});

test("publish rechecks progress and loading flags at the exact click", async () => {
  assert.equal(await task('publishReady', { schedule: true }), true);
  for (const width of ['99%', '99.9%', '100px']) {
    await tab.locator('.info-progress').evaluate((el, width) => { el.style.width = width; }, width);
    assert.equal(await task('publishReady', { schedule: true }), false);
    await assert.rejects(() => task('publish', { schedule: true, authorized: true }), /100%/);
  }
  await tab.locator('.info-progress').evaluate(el => { el.style.width = '100%'; });
  for (const attribute of ['data-disabled', 'data-loading', 'aria-disabled']) {
    await tab.locator('#publish').evaluate((el, attribute) => el.setAttribute(attribute, 'true'), attribute);
    assert.equal(await task('publishReady', { schedule: true }), false);
    await tab.locator('#publish').evaluate((el, attribute) => el.setAttribute(attribute, 'false'), attribute);
  }
  await tab.locator('.info-progress').evaluate(el => { el.style.visibility = 'hidden'; });
  assert.equal(await task('publishReady', { schedule: true }), false);
  await tab.locator('.info-progress').evaluate(el => el.remove());
  assert.equal(await task('publishReady', { schedule: true }), false);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
});

test("only an explicit opt-in clicks publish and repeated submissions are blocked", async () => {
  const result = await message(job({ publish: true }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  const again = await message(job({ type: "fill", publish: true }));
  assert.equal(again.ok, false);
  assert.match(again.error, /da bam/);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  const submissions = await dashboard.evaluate(async () => (await chrome.storage.local.get("submissions")).submissions);
  assert.equal(Object.values(submissions)[0].state, "success");
});

test('repost approval permits one new attempt, preserves receipt history and cannot be reused', async () => {
  const key = episodeKey(video);
  const old = { state: 'success', video, date: date + 'T20:00', at: '2026-01-01T00:00:00Z' };
  await dashboard.evaluate(({ key, old }) => chrome.storage.local.set({ submissions: { [key]: old, unrelated: { state: 'uncertain' } } }), { key, old });
  const request = job({ publish: true, repostReceipts: { [key]: old } });
  const result = await message(request); assert.equal(result.ok, true, result.error);
  const submissions = await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions);
  assert.equal(submissions[key].state, 'success'); assert.ok(submissions[key].repostAuthorizedAt);
  assert.deepEqual(submissions[key].previousAttempts, [old]);
  assert.deepEqual(submissions.unrelated, { state: 'uncertain' });
  const again = await message(request); assert.equal(again.ok, false); assert.match(again.error, /Bien nhan da thay doi/);
  assert.equal((await message(job({ type: 'fill', publish: true }))).ok, false);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  await tab.reload();
  const renewed = await message(job({ publish: true, repostReceipts: { [key]: submissions[key] } }));
  assert.equal(renewed.ok, true, renewed.error);
  const latest = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions).find(receipt => receipt.video));
  assert.equal(latest.previousAttempts.length, 2); assert.deepEqual(latest.previousAttempts[0], old);
  assert.equal(latest.previousAttempts[1].state, 'success'); assert.equal(latest.previousAttempts[1].previousAttempts, undefined);
});

test('repost approval is required for every repeated queue entry and rejects unselected or stale receipts', async () => {
  const folder = path.join(directory, 'repost-second'); await mkdir(folder, { recursive: true });
  const secondVideo = path.join(folder, 'second.mp4'); await writeFile(secondVideo, 'test bytes');
  const first = job().row, second = { ...first, id: 'repost-b', video: secondVideo };
  const keys = [episodeKey(first.video), episodeKey(second.video)];
  const receipts = Object.fromEntries([first, second].map(row => [episodeKey(row.video), { state: 'uncertain', video: row.video, date: row.gio_dang, at: 'old' }]));
  await dashboard.evaluate(submissions => chrome.storage.local.set({ submissions }), receipts);
  const base = job({ rows: [first, second], publish: true });
  for (const approvals of [{ [keys[0]]: receipts[keys[0]] }, { ...receipts, other: receipts[keys[0]] }, { ...receipts, [keys[0]]: { ...receipts[keys[0]], at: 'stale' } }]) {
    const result = await message({ ...base, repostReceipts: approvals }); assert.equal(result.ok, false);
    assert.equal(await tab.evaluate(() => window.clicks), 0);
    assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files.length), 0);
  }
  const result = await message({ ...base, repostReceipts: receipts }); assert.equal(result.ok, true, result.error);
  const latest = await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions);
  for (const key of keys) { assert.equal(latest[key].state, 'success'); assert.deepEqual(latest[key].previousAttempts, [receipts[key]]); }
});

test('repost approval does not discard a receipt when file preparation fails', async () => {
  const old = { state: 'success', video, date: date + 'T20:00', at: 'old' }, key = episodeKey(video);
  await dashboard.evaluate(submissions => chrome.storage.local.set({ submissions }), { [key]: old });
  const request = job({ publish: true, repostReceipts: { [key]: old } });
  request.row.video = path.join(directory, 'missing-repost.mp4');
  const result = await message(request); assert.equal(result.ok, false);
  assert.match(result.error, /Nạp video/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  assert.deepEqual(await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions), { [key]: old });
});

test('dashboard repost is off by default, cancellation does nothing and confirmed approval is one-shot', async () => {
  const row = { ...job().row, trang_thai: 'done', ghi_chu: '' }, key = episodeKey(video);
  const old = { state: 'success', video, date: row.gio_dang, at: 'old' };
  await dashboard.evaluate(({ row, key, old }) => chrome.storage.local.set({ rows: [row], checkedIds: [row.id], selected: row.id, scanSettings: { auto: false }, submissions: { [key]: old } }), { row, key, old });
  await dashboard.reload(); await expect(dashboard.locator('#prepare')).toBeEnabled();
  assert.equal(await dashboard.locator('#repost').isChecked(), false);
  await dashboard.locator('#publish').uncheck(); await expect(dashboard.locator('#repost')).toBeDisabled();
  await dashboard.locator('#publish').check(); await dashboard.locator('#repost').check();
  const cancelled = dashboard.waitForEvent('dialog'); const cancelClick = dashboard.locator('#prepare').click();
  const dialog = await cancelled; assert.match(dialog.message(), /tạo bài trùng/); assert.ok(dialog.message().includes(video)); await dialog.dismiss(); await cancelClick;
  await expect(dashboard.locator('#state')).toHaveText('Đã hủy');
  assert.equal(await dashboard.locator('#repost').isChecked(), false);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  assert.deepEqual(await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions), { [key]: old });
  await dashboard.locator('#repost').check();
  const confirmed = dashboard.waitForEvent('dialog'); const confirmClick = dashboard.locator('#prepare').click(); await (await confirmed).accept(); await confirmClick;
  await expect.poll(() => dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress?.status)).toBe('done');
  await expect(dashboard.locator('#prepare')).toBeEnabled();
  assert.equal(await dashboard.locator('#repost').isChecked(), false);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  for (const [name, width] of [['repost-desktop', 1280], ['repost-mobile', 390]]) {
    await dashboard.setViewportSize({ width, height: 900 });
    await expect(dashboard.locator('#repost')).toBeVisible();
    assert.equal(await dashboard.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await mkdir(path.join(root, 'test-results'), { recursive: true });
    await dashboard.screenshot({ path: path.join(root, 'test-results', name + '.png'), fullPage: true });
  }
  await dashboard.setViewportSize({ width: 1280, height: 900 });
});

test("queue advances only after success and stores every row result", async () => {
  const folder = path.join(directory, 'episode2'); await mkdir(folder, { recursive: true });
  const secondVideo = path.join(folder, 'second.mp4'); await writeFile(secondVideo, 'second fixture');
  const first = job().row, second = { ...first, id: 'b', video: secondVideo, tieu_de: 'Second' };
  const gated = await message(job({ rows: [first, second] }));
  assert.equal(gated.ok, false);
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files.length), 0);
  const result = await message(job({ rows: [first, second], publish: true }));
  assert.equal(result.ok, true, result.error);
  assert.equal(await tab.locator('[type="file"]').evaluate(el => el.files[0].name), 'second.mp4');
  const results = await dashboard.evaluate(async () => (await chrome.storage.local.get("rowResults")).rowResults);
  assert.equal(results.a.trang_thai, 'done'); assert.equal(results.b.trang_thai, 'done');
});

test("fill cannot publish an unknown draft but can finish one prepared by the extension", async () => {
  const unknown = await message(job({ type: 'fill', publish: true }));
  assert.equal(unknown.ok, false); assert.match(unknown.error, /Chua xac nhan ban nhap/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  const prepared = await message(job()); assert.equal(prepared.ok, true, prepared.error);
  const finished = await message(job({ type: 'fill', publish: true }));
  assert.equal(finished.ok, true, finished.error);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
});

test("a confirmation dialog stops the queue without repeating the click", async () => {
  await tab.evaluate(() => {
    document.querySelector('#publish').onclick = () => {
      window.clicks++;
      const modal = document.createElement('div'); modal.setAttribute('role', 'dialog'); modal.textContent = 'Confirm account'; document.body.append(modal);
    };
  });
  const result = await message(job({ publish: true }));
  assert.equal(result.ok, false);
  assert.match(result.error, /Confirm account/);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  const retry = await message(job({ type: 'fill', publish: true }));
  assert.equal(retry.ok, false);
  const submissions = await dashboard.evaluate(async () => (await chrome.storage.local.get("submissions")).submissions);
  assert.equal(Object.values(submissions)[0].state, 'uncertain');
});

test('copyright-incomplete confirmation is clicked once after upload, caption and schedule checks', async () => {
  await copyrightDialog();
  const result = await message(job({ publish: true })); assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 1);
  assert.equal(await task('scheduleCheck', { date, time: '20:00' }), true);
  const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(receipt.state, 'success'); assert.equal(receipt.confirmation.kind, 'copyright-incomplete');
  assert.equal(receipt.confirmation.state, 'attempted');
  const retry = await message(job({ type: 'fill', publish: true })); assert.equal(retry.ok, false);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 1);
});

test('video-checks confirmation without a copyright paragraph clicks the nested Dang ngay button once', async () => {
  await copyrightDialog({ copyright: false });
  const result = await message(job({ publish: true })); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => [window.clicks, window.confirmClicks]), [1, 1]);
  assert.equal(await task('scheduleCheck', { date, time: '20:00' }), true);
  const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(receipt.state, 'success'); assert.equal(receipt.confirmation.kind, 'video-checks-incomplete');
  const retry = await message(job({ type: 'fill', publish: true })); assert.equal(retry.ok, false);
  assert.deepEqual(await tab.evaluate(() => [window.clicks, window.confirmClicks]), [1, 1]);
});

test('fill resumes a 0.5.10 pending video-checks confirmation without changing the draft or clicking schedule again', async () => {
  const request = await pendingCopyrightConfirmation({ copyright: false });
  await dashboard.evaluate(async ({ tabId, schedule }) => {
    const { submissions } = await chrome.storage.local.get('submissions');
    Object.assign(Object.values(submissions)[0], { tabId, schedule });
    await chrome.storage.local.set({ submissions });
  }, request);
  const outcome = await task('publishOutcome');
  assert.equal(outcome.state, 'confirmation'); assert.equal(outcome.ready, true);
  assert.equal(outcome.kind, 'video-checks-incomplete');
  await tab.evaluate(() => {
    window.captionInputs = 0; window.fileChanges = 0;
    document.querySelector('[role="textbox"]').oninput = () => window.captionInputs++;
    document.querySelector('[type="file"]').onchange = () => window.fileChanges++;
  });
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => [window.clicks, window.confirmClicks, window.captionInputs, window.fileChanges]), [1, 1, 0, 0]);
});

test('fill resumes the legacy pending confirmation without reuploading, rewriting caption or clicking schedule', async () => {
  const request = await pendingCopyrightConfirmation();
  await tab.evaluate(() => {
    window.captionInputs = 0; window.fileChanges = 0;
    document.querySelector('[role="textbox"]').oninput = () => window.captionInputs++;
    document.querySelector('[type="file"]').onchange = () => window.fileChanges++;
  });
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => [window.clicks, window.confirmClicks, window.captionInputs, window.fileChanges]), [1, 1, 0, 0]);
});

test('pending copyright confirmation refuses changed date, video, caption or incomplete upload', async () => {
  for (const change of ['date', 'video', 'caption', 'upload']) {
    await tab.reload(); await dashboard.evaluate(() => chrome.storage.local.remove('submissions'));
    const request = await pendingCopyrightConfirmation();
    await tab.evaluate(change => {
      if (change === 'date') document.querySelector('[type="date"]').value = '2026-01-01';
      if (change === 'video') delete window.__omniVoiceDraftVideo;
      if (change === 'caption') document.querySelector('[role="textbox"]').textContent = 'Test #unexpected';
      if (change === 'upload') document.querySelector('.info-progress').style.width = '99%';
    }, change);
    const result = await message(request); assert.equal(result.ok, false, change);
    assert.equal(await tab.evaluate(() => window.clicks), 1);
    assert.equal(await tab.evaluate(() => window.confirmClicks), 0);
  }
});

test('a same-label button in an unrelated dialog or multiple dialogs is never confirmed', async () => {
  for (const scenario of ['unrelated', 'multiple', 'missing-checks', 'missing-question']) {
    await tab.reload(); await dashboard.evaluate(() => chrome.storage.local.remove('submissions'));
    const request = await pendingCopyrightConfirmation({ copyright: false });
    await tab.evaluate(scenario => {
      if (scenario === 'unrelated') document.querySelector('[role="dialog"] h2').textContent = 'Confirm account';
      else if (scenario === 'missing-checks') document.querySelector('[role="dialog"] p').textContent = 'Bạn có muốn tiếp tục đăng trước khi quy trình kiểm tra hoàn tất không?';
      else if (scenario === 'missing-question') document.querySelector('[role="dialog"] p').textContent = 'Chúng tôi vẫn đang kiểm tra video của bạn để phát hiện xem có vấn đề tiềm ẩn hay không.';
      else document.querySelector('[role="dialog"]').after(document.querySelector('[role="dialog"]').cloneNode(true));
    }, scenario);
    assert.equal((await task('publishOutcome')).state, 'dialog');
    await assert.rejects(() => task('confirmPublish', { authorized: true, schedule: true, date, time: '20:00', video, caption: 'Test' }), /san sang/);
    const result = await message(request); assert.equal(result.ok, false);
    assert.equal(await tab.evaluate(() => window.clicks), 1);
    assert.equal(await tab.evaluate(() => window.confirmClicks), 0);
  }
});

test('confirmation reservation prevents retry even when a second dialog interrupts the result', async () => {
  await copyrightDialog({ unknownAfter: true });
  const result = await message(job({ publish: true })); assert.equal(result.ok, false); assert.match(result.error, /Confirm account/);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 1);
  const retry = await message(job({ type: 'fill', publish: true })); assert.equal(retry.ok, false);
  const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(receipt.state, 'uncertain'); assert.equal(receipt.confirmation.state, 'attempted');
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 1);
});

test('explicit repost can retry a reserved pending confirmation without rewriting or clicking schedule again', async () => {
  const request = await pendingCopyrightConfirmation({ copyright: false });
  const key = episodeKey(video);
  const receipts = await dashboard.evaluate(async () => {
    const { submissions } = await chrome.storage.local.get('submissions');
    Object.values(submissions)[0].confirmation = { kind: 'video-checks-incomplete', state: 'attempted', at: 'old' };
    await chrome.storage.local.set({ submissions }); return submissions;
  });
  assert.equal((await message(request)).ok, false);
  request.repostReceipts = receipts;
  await tab.evaluate(() => {
    window.captionInputs = 0; window.fileChanges = 0;
    document.querySelector('[role="textbox"]').oninput = () => window.captionInputs++;
    document.querySelector('[type="file"]').onchange = () => window.fileChanges++;
  });
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.deepEqual(await tab.evaluate(() => [window.clicks, window.confirmClicks, window.captionInputs, window.fileChanges]), [1, 1, 0, 0]);
  const latest = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
  assert.equal(latest.state, 'success'); assert.equal(latest.confirmation.state, 'attempted');
  assert.deepEqual(latest.previousAttempts, [receipts[key]]);
  assert.equal((await message(request)).ok, false);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 1);
});

test('repost confirmation still checks upload, schedule and draft before replacing the prior receipt', async () => {
  const request = await pendingCopyrightConfirmation({ copyright: false });
  request.repostReceipts = await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions);
  for (const change of ['upload', 'schedule', 'draft']) {
    await tab.evaluate(change => {
      document.querySelector('.info-progress').style.width = change === 'upload' ? '99%' : '100%';
      document.querySelector('[type="time"]').value = change === 'schedule' ? '21:00' : '20:00';
      if (change === 'draft') delete window.__omniVoiceDraftVideo;
    }, change);
    const result = await message(request); assert.equal(result.ok, false, change);
    assert.equal(await tab.evaluate(() => window.confirmClicks), 0);
    assert.equal(await tab.evaluate(() => window.clicks), 1);
    assert.deepEqual(await dashboard.evaluate(async () => (await chrome.storage.local.get('submissions')).submissions), request.repostReceipts);
  }
});

test('stop interrupts a disabled copyright confirmation without clicking or reserving it', async () => {
  const request = await pendingCopyrightConfirmation({ disabled: true });
  const running = message(request);
  try {
    await expect.poll(() => dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress?.log.at(-1)?.includes('Tiếp tục hộp thoại'))).toBe(true);
    await message({ type: 'stop' });
    const result = await running; assert.equal(result.ok, false); assert.match(result.error, /Da dung/);
    assert.equal(await tab.evaluate(() => window.confirmClicks), 0);
    const receipt = await dashboard.evaluate(async () => Object.values((await chrome.storage.local.get('submissions')).submissions)[0]);
    assert.equal(receipt.confirmation, undefined);
  } finally { await message({ type: 'stop' }); await running; }
});

test('pending copyright confirmation still requires explicit publishing and matching stored schedule', async () => {
  const request = await pendingCopyrightConfirmation();
  const noPublish = await message({ ...request, publish: false }); assert.equal(noPublish.ok, false);
  const wrongSchedule = await message({ ...request, row: { ...request.row, gio_dang: date + 'T21:00' } }); assert.equal(wrongSchedule.ok, false);
  await tab.locator('[role="dialog"]').evaluate(el => el.remove());
  const gone = await message(request); assert.equal(gone.ok, false);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 0);
});

test('copyright confirmation rejects duplicate buttons and rechecks button flags and authorization at the click', async () => {
  const request = await pendingCopyrightConfirmation();
  const data = { authorized: true, schedule: true, date, time: '20:00', video, caption: 'Test' };
  await assert.rejects(() => task('confirmPublish', { ...data, authorized: false }), /Chua bat quyen/);
  await assert.rejects(() => task('confirmPublish', { ...data, video: undefined }), /da thay doi/);
  for (const attribute of ['aria-disabled', 'data-disabled', 'data-loading', 'aria-busy']) {
    await tab.locator('#confirm-post').evaluate((el, attribute) => el.setAttribute(attribute, 'true'), attribute);
    assert.equal((await task('publishOutcome')).ready, false);
    await assert.rejects(() => task('confirmPublish', data), /san sang/);
    await tab.locator('#confirm-post').evaluate((el, attribute) => el.removeAttribute(attribute), attribute);
  }
  await tab.locator('#confirm-post').evaluate(el => el.after(el.cloneNode(true)));
  assert.equal((await task('publishOutcome')).state, 'dialog');
  const result = await message(request); assert.equal(result.ok, false);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 0);
});

test('Vietnamese uppercase Dang buttons work for immediate publishing and its copyright confirmation', async () => {
  await tab.locator('#schedule').uncheck();
  await tab.locator('#publish').evaluate(el => { el.textContent = 'Đăng'; });
  await copyrightDialog();
  const request = job({ schedule: false, publish: true }); request.row.gio_dang = '';
  const result = await message(request); assert.equal(result.ok, true, result.error);
  assert.equal(await tab.evaluate(() => window.clicks), 1);
  assert.equal(await tab.evaluate(() => window.confirmClicks), 1);
  assert.equal(await tab.locator('#schedule').isChecked(), false);
});

test("stopping while publish is disabled never clicks and releases the queue lock", async () => {
  await tab.locator('#publish').evaluate(el => el.disabled = true);
  const request = job({ publish: true }); request.row.id = 'disabled-publish';
  const running = message(request);
  await expect.poll(() => dashboard.evaluate(async () => {
    const { progress } = await chrome.storage.local.get('progress');
    return progress?.status === 'running' && progress.rowId === 'disabled-publish' && progress.log.at(-1).includes('Dang cho tai/xu ly');
  })).toBe(true);
  await message({ type: 'stop' });
  const result = await running;
  assert.equal(result.ok, false); assert.match(result.error, /Da dung/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  assert.equal((await message({ type: 'status' })).running, false);
});

test("upload-complete messages are not publication receipts and default scheduling cannot cause an immediate post", async () => {
  await tab.locator('#outcome').evaluate(el => el.textContent = 'Video uploaded successfully');
  assert.equal((await task('publishOutcome')).state, 'waiting');
  assert.equal(await task('immediateCheck'), false);
  await tab.locator('#schedule').uncheck();
  assert.equal(await task('immediateCheck'), true);
});

test("side-panel configuration and the separate window use the same working dashboard", async () => {
  const manifest = await dashboard.evaluate(() => chrome.runtime.getManifest());
  assert.equal(manifest.side_panel.default_path, 'dashboard.html');
  assert.equal(await dashboard.locator('#publish').isChecked(), true);
  assert.equal(await dashboard.locator('#schedule').isChecked(), true);
  await dashboard.evaluate(row => chrome.storage.local.set({ rows: [{ ...row, trang_thai: 'cho', ghi_chu: '' }], checkedIds: [row.id], scanSettings: { auto: false } }), job().row);
  const opened = context.waitForEvent('page');
  await dashboard.locator('#popout').click();
  const popup = await opened; await popup.waitForLoadState();
  assert.equal(new URL(popup.url()).pathname, '/dashboard.html');
  await popup.setViewportSize({ width: 390, height: 844 });
  await popup.locator('#tab option').waitFor({ state: 'attached' });
  assert.equal(await popup.locator('#publish').isChecked(), true);
  assert.equal(await popup.locator('#schedule').isChecked(), true);
  assert.equal((await message({ type: 'status' })).running, false);
  assert.equal(await popup.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await mkdir(path.join(root, 'test-results'), { recursive: true });
  await popup.screenshot({ path: path.join(root, 'test-results', 'panel.png') });
  await popup.close();
});

test("schedule controls and date/time fields resolve aria-labelledby labels", async () => {
  await tab.setContent(`<span id="schedule-label">Schedule</span>
    <input id="schedule" type="checkbox" aria-labelledby="schedule-label" checked>
    <span id="date-label">Date</span><input aria-labelledby="date-label">
    <span id="time-label">Time</span><input aria-labelledby="time-label">`);
  assert.equal(await task('schedule'), 'already');
  assert.equal(await task('scheduleReady'), true);
  await task('setDate', { value: date }); await task('setTime', { value: '20:00' });
  assert.equal(await task('scheduleCheck', { date, time: '20:00' }), true);
  assert.equal((await task('scheduleSnapshot')).time.value, '20:00');
  assert.equal(await tab.locator('#schedule').isChecked(), true);
});

test("visible date fields do not mask ambiguous or disabled schedule controls", async () => {
  await tab.setContent(`<label><input type="checkbox">Schedule</label><label><input type="checkbox">Schedule</label>
    <input type="date" value="${date}"><input type="time" value="20:00">`);
  await assert.rejects(() => task('schedule'), /nhieu dieu khien/);
  assert.equal(await task('scheduleCheck', { date, time: '20:00' }), false);
  await tab.setContent('<label><input type="checkbox" disabled>Schedule</label>');
  await assert.rejects(() => task('schedule'), /bi khoa/);
});

test("scheduling errors expose the stage and persist expected and observed values", async () => {
  await tab.locator('#schedule').evaluate(el => { el.checked = false; el.disabled = true; });
  const result = await message(job());
  assert.equal(result.ok, false); assert.match(result.error, /\[Bật lên lịch\]/);
  const diagnostic = await dashboard.evaluate(async () => (await chrome.storage.local.get('lastDiagnostic')).lastDiagnostic);
  assert.equal(diagnostic.expectedSchedule, date + 'T20:00');
  assert.equal(diagnostic.version, await dashboard.evaluate(() => chrome.runtime.getManifest().version));
  assert.deepEqual(diagnostic.selectors, {});
  assert.equal(diagnostic.frames[0].schedule.controls[0].disabled, true);
  await dashboard.locator('#operation-error').waitFor({ state: 'visible' });
  assert.match(await dashboard.locator('#operation-error').innerText(), /bi khoa/);
  assert.equal(await tab.evaluate(() => window.clicks), 0);
  await dashboard.setViewportSize({ width: 390, height: 844 });
  assert.equal(await dashboard.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await dashboard.screenshot({ path: path.join(root, 'test-results', 'schedule-error.png') });
});

test("restored errors are labeled as history, while a new run gets the current version", async () => {
  const oldError = '19:22:28 Chua xac nhan duoc file. Kiem tra duong dan va quyen truy cap file URL cua extension.';
  await dashboard.evaluate(log => chrome.storage.local.set({ progress: { status: 'error', log: [log] } }), oldError);
  await dashboard.reload();
  await dashboard.locator('#tab option').waitFor({ state: 'attached' });
  assert.match(await dashboard.locator('#operation-error').innerText(), /Lần chạy trước/);
  assert.match(await dashboard.locator('#state').innerText(), /Lần chạy trước/);
  const version = await dashboard.evaluate(() => chrome.runtime.getManifest().version);
  assert.equal(await dashboard.locator('#build-version').innerText(), 'v' + version);
  const result = await message(job({ schedule: false }));
  assert.equal(result.ok, true, result.error);
  const progress = await dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress);
  assert.equal(progress.version, version);
  assert.ok(Number.isFinite(Date.parse(progress.updatedAt)));
  assert.equal(await dashboard.locator('#operation-error').isHidden(), true);
  assert.doesNotMatch(await dashboard.locator('#log').innerText(), /19:22:28|Lần chạy trước/);
});
