import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

test('Blender projects resume after refresh, resize locally, and export editable engineering files', async ({ page }) => {
  const blender = await (await page.request.get('/api/blender')).json();
  test.skip(!blender.ready, 'Install Blender to run the real local rebuilding test.');
  const part = JSON.parse(await fs.readFile('examples/U形理线夹-6毫米孔.json', 'utf8'));
  const older = JSON.parse(await fs.readFile('examples/牛油果椅子.json', 'utf8'));
  const created: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', async response => {
    if (response.url().endsWith('/api/generate') && response.request().method() === 'POST' && response.ok()) {
      created.push((await response.json()).id);
    }
  });
  try {
    await page.goto('/');
    await expect(page.getByRole('button', { name: '生成我的模型' })).toBeEnabled();
    // Hold the UI at an in-flight state, while the real local Blender job runs.
    await page.route('**/api/jobs/*', route => route.fulfill({ json: {
      id: created[0], status: 'running', engine: 'blender', stage: '本地 Blender 正在建模', progress: 50,
    } }));
    const response = page.waitForResponse(r => r.url().endsWith('/api/generate') && r.request().method() === 'POST');
    await page.locator('input[accept=".json,application/json"]').setInputFiles({
      name: 'part.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(part)),
    });
    const id = (await (await response).json()).id;
    await expect(page.locator('.generation-overlay')).toBeVisible();
    await expect.poll(async () => (await (await page.request.get('/api/jobs/' + id)).json()).status,
      { timeout: 30000 }).toBe('complete');
    await expect.poll(() => page.evaluate(() => localStorage.getItem('xiaozao.active-job'))).toBe(id);
    await page.unroute('**/api/jobs/*');
    // An older history entry must not overwrite the resumed model's description.
    await page.route('**/api/models', route => route.request().method() === 'GET'
      ? route.fulfill({ json: [older] }) : route.continue());
    await page.reload();
    await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 30000 });
    await expect(page.locator('.model-name h2')).toHaveText(part.recipe.name);
    await expect(page.getByLabel('你想做点什么？')).toHaveValue(part.recipe.prompt);
    await expect(page.getByLabel('创作方式', { exact: true })).toHaveValue('blender');
    await expect(page.getByRole('button', { name: '用 Blender 打开', exact: true })).toBeVisible();
    await page.unroute('**/api/models');
    const next = page.waitForResponse(r => r.url().endsWith('/api/generate') && r.request().method() === 'POST');
    await page.getByLabel('高度', { exact: true }).fill('56');
    await page.getByRole('button', { name: '应用修改' }).click();
    const resizedId = (await (await next).json()).id;
    await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 30000 });
    await expect(page.getByLabel('高度', { exact: true })).toHaveValue('56');
    const resized = await (await page.request.get('/api/models/' + resizedId)).json();
    expect(resized.stats.dimensions).toEqual([72, 40, 56]);
    expect(resized.stats.watertight).toBe(true);
    expect(resized.recipe.code).toBe(part.recipe.code);
    await page.getByRole('button', { name: '导出打印文件', exact: true }).click();
    for (const [name, extension] of [
      ['下载可编辑 Blender 工程（.blend）', '.blend'], ['下载 3MF 文件', '.3mf'],
    ]) {
      const event = page.waitForEvent('download');
      await page.getByRole('button', { name, exact: true }).click();
      const download = await event;
      expect(download.suggestedFilename()).toContain(extension);
      expect((await fs.stat((await download.path())!)).size).toBeGreaterThan(1000);
    }
    expect(errors).toEqual([]);
  } finally {
    for (const id of created) await page.request.delete('/api/models/' + id);
  }
});
