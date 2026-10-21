import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, writeFile, readdir } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const folder = resolve(root, 'tmp/web-tests');
await mkdir(folder, { recursive: true });
const base = process.env.PDF_WATERMARK_TEST_URL || 'http://127.0.0.1:4173/';
const executablePath = process.env.PDF_WATERMARK_BROWSER_PATH;
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
const requests = [], errors = [], outputs = [];
context.on('request', request => {
  // Edge's own download panel loads edge:// resources; these are browser UI,
  // not network requests made by the application. Inspect all HTTP(S) traffic.
  if (/^https?:/.test(request.url())) requests.push({ url: request.url(), method: request.method() });
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
await page.goto(base);

async function processPDF(source, customer, label, extra = {}) {
  await page.locator('#template').setInputFiles(source);
  await page.locator('#customer').fill(customer);
  if (extra.header !== undefined) {
    await page.locator('details').evaluate(element => { element.open = true; });
    await page.locator('#header').fill(extra.header);
  }
  const started = Date.now();
  await page.locator('#generate').click();
  await page.waitForFunction(() => !document.querySelector('#result').hidden || document.querySelector('#status').classList.contains('error'), null, { timeout: 120000 });
  const error = await page.locator('#status').textContent();
  if (extra.reject) {
    assert.ok(error, `${label}: expected rejection`);
    assert.equal(await page.locator('#result').isVisible(), false);
    assert.equal(await page.locator('#download').getAttribute('href'), null);
    console.log(`PASS reject ${label}: ${error}`);
    return;
  }
  assert.equal(error, '', `${label}: ${error}`);
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download').click()]);
  const target = resolve(folder, `browser-${label}.pdf`);
  await download.saveAs(target);
  outputs.push({ source, output: target, customer, header: extra.header || `Prepared exclusively for ${customer}` });
  console.log(`PASS ${label} (${Date.now() - started} ms)`);
}

try {
  await processPDF(resolve(folder, 'mixed.pdf'), 'Bank of Ireland', 'mixed');
  await processPDF(resolve(folder, 'mixed.pdf'), 'Bank of Ireland', 'repeat');
  await processPDF(resolve(folder, 'mixed.pdf'), 'Müller & Co.', 'unicode', { header: 'Confidential - Müller & Co.' });
  await page.locator('#header').fill('');
  for (const angle of [0, 90, 180, 270]) {
    await processPDF(resolve(folder, `rotation-${angle}.pdf`), 'Example Corporation', `rotation-${angle}`);
  }
  for (const kind of ['form', 'signature', 'widget', 'scaled', 'encrypted', 'password', 'invalid']) {
    await processPDF(resolve(folder, `${kind}.pdf`), 'Example Corporation', kind, { reject: true });
  }
  await processPDF(resolve(folder, 'mixed.pdf'), '客户', 'missing-font', { reject: true });
  await processPDF(resolve(folder, 'mixed.pdf'), 'Acme', 'long-header', { header: 'Very long header '.repeat(18), reject: true });
  await page.locator('#header').fill('');
  // A failed job must not poison the next job's WebAssembly instance.
  await processPDF(resolve(folder, 'mixed.pdf'), 'Example Corporation', 'after-errors');
  if (process.env.PDF_WATERMARK_TEST_TEMPLATE) {
    await processPDF(resolve(process.env.PDF_WATERMARK_TEST_TEMPLATE), 'Example Corporation', 'external-template');
  }
  await page.screenshot({ path: resolve(folder, 'desktop.png'), fullPage: true });
  // Check responsive layout and error/success announcement contracts.
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({ path: resolve(folder, 'mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator('#template').setInputFiles(resolve(folder, 'mixed.pdf'));
  await page.locator('#customer').fill('Cancel Test');
  await page.locator('#generate').click();
  await page.locator('#cancel').click();
  assert.match(await page.locator('#status').textContent(), /cancelled/);
  assert.equal(await page.locator('#generate').isEnabled(), true);
  assert.equal(await page.locator('#download').getAttribute('href'), null);
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.deepEqual(errors, []);
  const origin = new URL(base).origin;
  assert.ok(requests.every(request => request.method === 'GET' && new URL(request.url).origin === origin), JSON.stringify(requests));
  assert.ok(requests.every(request => !request.url.toLowerCase().includes('.pdf')), 'A document was requested over HTTP');
  console.log(`PASS privacy: ${requests.length} same-origin static GETs, no PDF requests, no browser storage`);
  await writeFile(resolve(folder, 'manifest.json'), JSON.stringify(outputs, null, 2));
  await writeFile(resolve(folder, 'requests.json'), JSON.stringify(requests, null, 2));
} finally { await browser.close(); }
