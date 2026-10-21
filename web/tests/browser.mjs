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

async function setRange(id, value) {
  await page.locator(`#${id}`).evaluate((element, selected) => {
    element.value = selected;
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, String(value));
}

async function previewStyle() {
  return page.locator('#preview-watermark').evaluate(element => {
    const style = getComputedStyle(element);
    return { opacity: Number(style.opacity), size: parseFloat(style.fontSize) };
  });
}

async function processPDF(source, customer, label, extra = {}) {
  await page.locator('#template').setInputFiles(source);
  await page.locator('#customer').fill(customer);
  if (extra.header !== undefined) {
    await page.locator('details').evaluate(element => { element.open = true; });
    await page.locator('#header').fill(extra.header);
  }
  if (extra.watermarkFontSize !== undefined) await setRange('watermark-size', extra.watermarkFontSize);
  if (extra.opacity !== undefined) await setRange('opacity', extra.opacity);
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
  outputs.push({ source, output: target, customer, header: extra.header || `Prepared exclusively for ${customer}`,
    expectedFontSize: extra.watermarkFontSize, opacity: Number(await page.locator('#opacity').inputValue()) / 100 });
  console.log(`PASS ${label} (${Date.now() - started} ms)`);
}

try {
  await page.evaluate(() => document.fonts.ready);
  assert.equal((await previewStyle()).opacity, 0.16);
  assert.equal(await page.locator('h1').textContent(), 'Prepare your document');
  assert.equal(await page.getByText('A white paper.').count(), 0);
  await processPDF(resolve(folder, 'mixed.pdf'), 'Bank of Ireland', 'mixed');
  await processPDF(resolve(folder, 'mixed.pdf'), 'Bank of Ireland', 'repeat');
  await page.locator('details').evaluate(element => { element.open = true; });
  await processPDF(resolve(folder, 'mixed.pdf'), 'Acme', 'small-watermark', { watermarkFontSize: 12, opacity: 5 });
  const small = await previewStyle();
  assert.equal(small.opacity, 0.05);
  assert.equal(await page.locator('#watermark-size-label').textContent(), '12 pt');
  await page.locator('#watermark-size').focus();
  await page.locator('#watermark-size').press('End');
  assert.equal(await page.locator('#result').isVisible(), false);
  const large = await previewStyle();
  assert.ok(Math.abs(large.size / small.size - 8) < 0.01, 'Font size did not update the preview');
  assert.equal(await page.locator('#watermark-size-label').textContent(), '96 pt');
  await page.locator('#opacity').focus();
  await page.locator('#opacity').press('End');
  assert.equal((await previewStyle()).opacity, 0.4);
  assert.equal(await page.locator('#opacity-label').textContent(), '40%');
  await processPDF(resolve(folder, 'mixed.pdf'), 'Acme', 'large-watermark', { watermarkFontSize: 96, opacity: 40 });
  await page.screenshot({ path: resolve(folder, 'customized.png'), fullPage: true });
  // Appearance changes must invalidate a previously generated download.
  await setRange('opacity', 16);
  assert.equal(await page.locator('#result').isVisible(), false);
  assert.equal(await page.locator('#download').getAttribute('href'), null);
  await setRange('watermark-size', 48);
  console.log('PASS live size/opacity preview, keyboard sliders and stale download invalidation');
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
