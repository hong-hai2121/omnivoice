// Manual check: with rows but nothing ticked, the dashboard shows why Nạp & điền is locked.
// node tests/check_blocked_reason.mjs  → prints the reason and saves test-results/blocked-reason.png
import { chromium } from '@playwright/test';
import { mkdtemp, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { isolatedExtension } from './helpers.mjs';

const directory = await mkdtemp(path.join(tmpdir(), 'omni-reason-'));
const extension = await isolatedExtension(directory);
const context = await chromium.launchPersistentContext(path.join(directory, 'profile'), {
  headless: true, channel: 'chromium', args: ['--disable-extensions-except=' + extension, '--load-extension=' + extension],
});
try {
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  await context.route('http://127.0.0.1:8771/**', route => route.fulfill({ contentType: 'application/json', body: '{"ok":true,"muc":[]}' }));
  const dashboard = await context.newPage();
  await dashboard.setViewportSize({ width: 420, height: 760 });
  await dashboard.goto('chrome-extension://' + new URL(worker.url()).host + '/dashboard.html');
  await dashboard.locator('#add').click();
  const state = dashboard.locator('#action-state');
  console.log('after add  :', await dashboard.locator('#prepare').isEnabled(), '|', await state.innerText());
  await dashboard.locator('#clear-selection').click();
  console.log('no selection:', await dashboard.locator('#prepare').isDisabled(), '| class=' + await state.getAttribute('class'), '|', await state.innerText());
  console.log('tooltip     :', await dashboard.locator('#prepare').getAttribute('title'));
  await mkdir('test-results', { recursive: true });
  await dashboard.screenshot({ path: 'test-results/blocked-reason.png' });
} finally {
  await context.close();
  await rm(directory, { recursive: true, force: true });
}
