import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

for (const width of [1440, 390]) {
  test(`fine modeling defaults and existing design refinement at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const original = JSON.parse(await fs.readFile('examples/U形理线夹-6毫米孔.json', 'utf8'));
    const mesh = await fs.readFile('examples/U形理线夹-6毫米孔.stl');
    const payloads: Record<string, unknown>[] = [];
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/models', route => route.fulfill({ json: [original] }));
    await page.route('**/api/models/*/download/stl', route => route.fulfill({ contentType: 'application/octet-stream', body: mesh }));
    await page.route('**/api/models/*/thumbnail', route => route.fulfill({ json: { ok: true } }));
    await page.route('**/api/generate', async route => {
      payloads.push(route.request().postDataJSON());
      await route.fulfill({ json: { id: 'f'.repeat(32) } });
    });
    await page.route('**/api/jobs/*', route => route.fulfill({ json: {
      id: 'f'.repeat(32), status: 'complete', progress: 100, stage: '完成', engine: 'blender',
      model: { ...original, recipe: { ...original.recipe, detail: 'fine', refinement: 'refined', review: '已复核通孔和接触面。' } },
    } }));
    await page.goto('/');
    await expect(page.getByRole('button', { name: '生成我的模型' })).toBeEnabled();
    await expect(page.getByLabel('造型精细程度')).toHaveValue('fine');
    await expect(page.getByText('细化轮廓与局部结构；生成预览会发给大模型复核，增加一次调用，通常需要数分钟。')).toBeVisible();
    await page.getByLabel('造型精细程度').selectOption('draft');
    await page.getByRole('button', { name: '精修当前作品', exact: true }).click();
    await expect(page.locator('.generation-overlay')).toHaveCount(0);
    await expect(page.getByLabel('造型精细程度')).toHaveValue('fine');
    expect(payloads).toHaveLength(1);
    expect(payloads[0].detail).toBe('fine');
    expect((payloads[0].previous as { code: string }).code).toBe(original.recipe.code);
    await page.getByText('查看造型复核说明', { exact: true }).click();
    await expect(page.getByText('已复核通孔和接触面。', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    expect(errors).toEqual([]);
  });
}
