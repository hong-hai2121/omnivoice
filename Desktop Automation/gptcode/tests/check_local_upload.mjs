// Read one byte from an actual episode file through the extension, never upload to TikTok.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const episode = process.argv[2];
if (!/^\d+$/.test(episode || "")) throw new Error("Usage: node tests/check_local_upload.mjs EPISODE_NUMBER");
const response = await fetch("http://127.0.0.1:8771/api/scan", { headers: { "X-Omni": "gptcode-scanner" } });
const data = await response.json();
assert.ok(response.ok && data.ok);
const matches = data.muc.filter(row => row.hashtag.split(/\s+/).includes('#MimiAudioSo' + episode));
assert.equal(matches.length, 1, "Expected exactly one matching episode");
const row = { ...matches[0], id: "local-upload-check" };
const file = await stat(row.video);
const root = fileURLToPath(new URL("../", import.meta.url));
const profile = await mkdtemp(path.join(tmpdir(), "gptcode-local-upload-"));
let context;
try {
  const extension = path.join(root, 'extension');
  context = await chromium.launchPersistentContext(profile, {
    headless: true, channel: 'chromium', args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  // All HTTP requests from the isolated browser are intercepted or aborted.
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.protocol === 'chrome-extension:') return route.continue();
    if (url.origin === 'https://www.tiktok.com') return route.fulfill({ contentType: 'text/html', body: `
      <input type="file" accept="video/*"><div role="textbox" contenteditable="true" style="width:500px;height:90px"></div>
      <script>document.querySelector('input').onchange=event=>{
        const f=event.target.files[0]; window.received={name:f.name,size:f.size}; event.target.value=''; event.target.remove();
      };</script>` });
    if (url.origin === 'http://127.0.0.1:8771') return route.fulfill({ contentType: 'application/json', body: '{"ok":true,"muc":[]}' });
    return route.abort();
  });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const tab = await context.newPage(); await tab.goto('https://www.tiktok.com/tiktokstudio/upload');
  const dashboard = await context.newPage(); await dashboard.goto(`chrome-extension://${new URL(worker.url()).host}/dashboard.html`);
  await dashboard.locator('#tab option').waitFor({ state: 'attached' });
  const tabId = Number(await dashboard.locator('#tab').inputValue());
  const result = await dashboard.evaluate(request => chrome.runtime.sendMessage(request), {
    type: 'prepare', tabId, row, schedule: false, publish: false,
  });
  assert.equal(result.ok, true, result.error);
  const received = await tab.evaluate(() => window.received);
  assert.equal(received.name, path.basename(row.video)); assert.equal(received.size, file.size);
  const progress = await dashboard.evaluate(async () => (await chrome.storage.local.get('progress')).progress);
  assert.equal(progress.status, 'review');
  console.log(JSON.stringify({ episode, bytes: received.size, filename: received.name, version: progress.version, result: 'verified; no real upload or post' }));
} finally {
  await context?.close();
  if (profile.startsWith(path.join(tmpdir(), 'gptcode-local-upload-'))) await rm(profile, { recursive: true, force: true });
}
