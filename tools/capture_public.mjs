// Start the disposable server first: node tools/e2e-server.mjs
// Then run this script with a Playwright Chromium installation or CHROME_PATH.
// The model is a public example loaded through mocked routes; no paid calls.
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
const example = JSON.parse(await fs.readFile('examples/牛油果椅子.json', 'utf8'));
const mesh = await fs.readFile('examples/牛油果椅子.stl');
example.id = 'a'.repeat(32);
example.created_at = 1795046400;
example.stats.warnings = ['公开演示示例，打印前确认壁厚与支撑。'];
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined,
  args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] });
try {
  await fs.mkdir('docs/assets', { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/models', route => route.fulfill({ json: [example] }));
  await page.route('**/api/models/*/download/stl', route => route.fulfill({ body: mesh }));
  await page.route('**/api/models/*/thumbnail', route => route.fulfill({ json: { ok: true } }));
  await page.route('**/api/generate', route => route.abort());
  await page.goto('http://127.0.0.1:8766');
  await page.locator('.model-name h2').filter({ hasText: example.name }).waitFor();
  await page.waitForFunction(() => document.querySelector('canvas')?.width > 0);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'docs/assets/workbench-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  if (await page.evaluate(() => document.documentElement.scrollWidth) !== 390) throw new Error('Mobile overflow');
  await page.screenshot({ path: 'docs/assets/workbench-mobile.png', fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('Public example screenshots captured without private data or paid requests.');
} finally {
  await browser.close();
}
