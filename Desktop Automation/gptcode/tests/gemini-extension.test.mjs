import {test, before, after} from "node:test";
import assert from "node:assert/strict";
import {chromium, expect} from "@playwright/test";
import {mkdtemp, readFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {spawn} from "node:child_process";

const root = fileURLToPath(new URL("../../../", import.meta.url));
// Never use the application port 17863 here: the user's real Chrome extension polls it
// and would execute the test commands (02/10/2026 it opened Gemini tabs that way).
const TEST_PORT = 17899;
const pythonEnv = {...process.env, PYTHONIOENCODING: "utf-8", OMNI_TEST_BRIDGE_PORT: String(TEST_PORT)};
let context, worker, popup, directory, python;
let submissions = [];
const fixture = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<div class="ql-editor" role="textbox" contenteditable="true" style="width:500px;height:130px"></div>
<button aria-label="Send message">Gửi</button><section id="answers"></section>
<script>
document.querySelector('button').onclick = () => {
  const editor = document.querySelector('.ql-editor');
  const text = editor.innerText;
  window.recordSubmission(text);
  editor.innerHTML = '';
  const response = document.createElement('message-content');
  response.style.display = 'block';
  response.textContent = 'Bản dịch thử nghiệm ' + document.querySelectorAll('message-content').length + ': Một ngày đẹp trời, chúng tôi cùng nhau đi dạo trong công viên và kể cho nhau nghe những câu chuyện vui vẻ.';
  document.querySelector('#answers').append(response);
};
</script></body></html>`;

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "omnivoice-gemini-test-"));
  const extension = path.join(root, "chrome_gemini_extension");
  context = await chromium.launchPersistentContext(path.join(directory, "profile"), {
    headless: true, channel: "chromium",
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`,
      "--host-resolver-rules=MAP gemini.google.com ~NOTFOUND"]
  });
  await context.exposeFunction("recordSubmission", text => submissions.push(text));
  await context.route("https://gemini.google.com/**", route => route.fulfill({contentType: "text/html", body: fixture}));
  worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  // Playwright cannot route the first request of an extension-created target
  // until attached. Create about:blank first so every Gemini request is mocked.
  await worker.evaluate(() => {
    const create = chrome.tabs.create.bind(chrome.tabs);
    chrome.tabs.create = async properties => {
      const tab = await create({...properties, url: "about:blank"});
      await new Promise(resolve => setTimeout(resolve, 300));
      return chrome.tabs.update(tab.id, {url: properties.url});
    };
  });
  await worker.evaluate(port => chrome.storage.local.set({bridgePort: port}), TEST_PORT);
  popup = await context.newPage();
  await popup.goto(`chrome-extension://${new URL(worker.url()).host}/popup.html`);
});

after(async () => {
  if (python && python.exitCode === null) python.kill();
  await context?.close();
  // Only the mkdtemp-created test directory is removed.
  if (directory?.startsWith(path.join(tmpdir(), "omnivoice-gemini-test-"))) {
    await rm(directory, {recursive: true, force: true});
  }
});

test("installed MV3 extension connects Python, submits Unicode, saves DOCX and resumes", {timeout: 60000}, async () => {
  python = spawn(path.join(root, "venv/Scripts/python.exe"), ["-u",
    path.join(root, "myvoice/tests/gemini_browser_fixture.py"), directory],
    {cwd: root, windowsHide: true, env: pythonEnv});
  let output = "", errors = "";
  python.stdout.on("data", chunk => { output += chunk; });
  python.stderr.on("data", chunk => { errors += chunk; });
  const completed = new Promise(resolve => python.on("close", code => resolve(code)));
  await expect.poll(() => output, {timeout: 10000}).toContain("BRIDGE_READY");
  // Installing auto-connects with the default code; the popup shows it pre-filled.
  await popup.reload();
  assert.equal(await popup.locator("#token").inputValue(), "omnivoice-gemini-local");
  const installed = await worker.evaluate(() => chrome.storage.local.get(["token", "enabled"]));
  assert.deepEqual(installed, {token: "omnivoice-gemini-local", enabled: true});
  await popup.locator("#token").fill("test-extension-token");
  await popup.locator("#connect").click();
  const code = await completed;
  assert.equal(code, 0, errors + output);
  assert.match(output, /"paragraphs": 2/);
  assert.equal(submissions.length, 3, "one instruction + two chunks, no duplicate on resume");
  assert.equal(submissions[0], "Hãy dịch tiếng Trung sang tiếng Việt.");
  assert.match(submissions[1], /你好，今天的天气很好。/);
  assert.match(submissions[2], /我们一起去公园散步。/);
});

test("content script blocks submit while streaming and rejects a closed Gemini tab", async () => {
  const {tabId} = await worker.evaluate(() => chrome.storage.session.get("tabId"));
  const page = context.pages().find(page => page.url().startsWith("https://gemini.google.com"));
  await page.evaluate(() => {
    const stop = document.createElement("button");
    stop.setAttribute("aria-label", "Stop response"); stop.textContent = "Stop";
    document.body.append(stop);
  });
  const result = await worker.evaluate(async tabId => chrome.tabs.sendMessage(tabId, {
    source: "omnivoice", action: "submit", id: "blocked-stream", text: "Do not send",
    editor_selectors: [".ql-editor"], send_selectors: ["button[aria-label='Send message']"]
  }), tabId);
  assert.match(result.error, /vẫn đang trả lời/);
  assert.equal(submissions.length, 3);
  await page.close();
  await assert.rejects(worker.evaluate(tabId => chrome.tabs.sendMessage(tabId, {source: "omnivoice", action: "ready"}), tabId));
});

test("GUI checkboxes select exactly one browser and synchronize both Home forms", async () => {
  const page = await context.newPage();
  await page.setContent([1, 2].map(i => `<form id="form${i}">
    <input type="checkbox" name="gemini_backend" value="firefox" checked>
    <input type="checkbox" name="gemini_backend" value="extension">
  </form>`).join(""));
  await page.addScriptTag({content: await readFile(path.join(root, "myvoice/web/static/app.js"), "utf8")});
  await page.locator('#form1 input[value="extension"]').click();
  assert.equal(await page.locator('input[value="extension"]:checked').count(), 2);
  assert.equal(await page.locator('input[value="firefox"]:checked').count(), 0);
  await page.locator('#form2 input[value="extension"]').click();
  assert.equal(await page.locator('input[value="extension"]:checked').count(), 2);
  await page.locator('#form2 input[value="firefox"]').click();
  assert.equal(await page.locator('input[value="firefox"]:checked').count(), 2);
  assert.equal(await page.locator('input[value="extension"]:checked').count(), 0);
  await page.close();
});

test("a wrong saved code (the web page's ?token=) heals to the default code", {timeout: 60000}, async () => {
  // Reproduces 02/10/2026: the web control panel's ?token= was pasted into the popup.
  await worker.evaluate(() => chrome.storage.local.set({token: "J3VMzIHTXChi", enabled: true}));
  const scripts = path.join(root, "myvoice", "scripts");
  const code = [
    "import sys",
    `sys.path.insert(0, ${JSON.stringify(scripts)})`,
    "from gemini_backend import DEFAULT_TOKEN",
    "from gemini_extension import ExtensionBridge",
    `bridge = ExtensionBridge(port=${TEST_PORT}, token=DEFAULT_TOKEN)`,
    "print('READY', flush=True)",
    "ok = bridge.wait_for_client(40)",
    "bridge.close()",
    "print('CONNECTED' if ok else 'TIMEOUT', 'bad_auth=%d' % bridge.bad_auth, flush=True)",
  ].join("\n");
  const healer = spawn(path.join(root, "venv/Scripts/python.exe"), ["-u", "-c", code],
    {cwd: root, windowsHide: true, env: pythonEnv});
  let output = "", errors = "";
  healer.stdout.on("data", chunk => { output += chunk; });
  healer.stderr.on("data", chunk => { errors += chunk; });
  const exited = new Promise(resolve => healer.on("close", resolve));
  await expect.poll(() => output, {timeout: 10000}).toContain("READY");
  // Reset the idle back-off so the next poll happens right away.
  await popup.evaluate(() => chrome.runtime.sendMessage({type: "connect"}));
  assert.equal(await exited, 0, errors + output);
  assert.match(output, /CONNECTED bad_auth=[1-9]/, "first poll rejected, retry with default accepted");
  const saved = await worker.evaluate(() => chrome.storage.local.get("token"));
  assert.equal(saved.token, "omnivoice-gemini-local");
});

test("next episode reuses the one Gemini tab; a tab taken elsewhere is left alone", {timeout: 90000}, async () => {
  // The web queue runs every episode in its own Python process = a new bridge session.
  const scripts = path.join(root, "myvoice", "scripts");
  const code = [
    "import sys",
    `sys.path.insert(0, ${JSON.stringify(scripts)})`,
    "from gemini_backend import DEFAULT_TOKEN",
    "from gemini_extension import ChromeExtensionDriver, ExtensionBridge",
    `driver = ChromeExtensionDriver('https://gemini.google.com/app', bridge=ExtensionBridge(port=${TEST_PORT}, token=DEFAULT_TOKEN))`,
    "print('URL', driver.current_url, flush=True)",
    "driver.quit()",
  ].join("\n");
  async function episode() {
    const child = spawn(path.join(root, "venv/Scripts/python.exe"), ["-u", "-c", code],
      {cwd: root, windowsHide: true, env: pythonEnv});
    let output = "", errors = "";
    child.stdout.on("data", chunk => { output += chunk; });
    child.stderr.on("data", chunk => { errors += chunk; });
    const status = await new Promise(resolve => child.on("close", resolve));
    assert.equal(status, 0, errors + output);
    assert.match(output, /URL https:\/\/gemini\.google\.com\//);
  }
  // Tabs are compared as Playwright pages (the worker's view of extension storage is
  // not reliable from the test, and the extension cannot read about:blank URLs).
  const geminiPages = () => context.pages().filter(page => page.url().startsWith("https://gemini.google.com/"));
  const pagesBefore = context.pages().length;
  await episode();
  const [first] = geminiPages();
  assert.ok(first, "episode 1 opened a Gemini tab");
  await episode();
  assert.deepEqual(geminiPages(), [first], "episode 2 must reuse the tab of episode 1");
  assert.ok(context.pages().length <= pagesBefore + 1, "at most one tab opened for two episodes");
  // The user took the working tab to another page: never navigate it away.
  await first.goto("about:blank");
  await new Promise(resolve => setTimeout(resolve, 1000));   // let Chrome's tab state settle
  await episode();
  assert.equal(first.url(), "about:blank", "a tab no longer on Gemini is left alone");
  assert.equal(geminiPages().length, 1);
  assert.notEqual(geminiPages()[0], first);
});
