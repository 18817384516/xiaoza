import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

for (const width of [1440, 390]) {
  test(`reference generation preserves unprintable detail and original download at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1050 });
    const base = JSON.parse(await fs.readFile('examples/U形理线夹-6毫米孔.json', 'utf8'));
    const mesh = await fs.readFile('examples/U形理线夹-6毫米孔.stl');
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const payloads: Record<string, unknown>[] = [];
    const model = { ...base, id: 'b'.repeat(32), name: '参考图角色',
      recipe: { kind: 'meshy', name: '参考图角色', category: 'figurine', prompt: '角色，高120毫米', params: { height: 120 } },
      stats: { ...base.stats, print_ready: false, watertight: false, components: 2,
        warnings: ['完整形象已保留，打印网格待修复。'] } };
    await page.route('**/api/models', route => route.fulfill({ json: [] }));
    await page.route('**/api/settings', route => route.fulfill({ json: {
      enabled: true, base_url: 'https://example.com/v1', model: 'vision-model', has_key: true,
      has_meshy_key: true, meshy_texture: true,
    } }));
    await page.route('**/api/models/*/preview.stl', route => route.fulfill({ body: mesh }));
    await page.route('**/api/models/*/thumbnail', route => route.fulfill({ json: { ok: true } }));
    await page.route('**/api/models/*/download/glb', route => route.fulfill({ body: Buffer.from('mock-original-GLB') }));
    await page.route('**/api/generate', async route => {
      const body = route.request().postDataJSON();
      payloads.push(body);
      model.recipe = { ...model.recipe, ...body, kind: 'meshy', name: '参考图角色' };
      await route.fulfill({ json: { id: model.id } });
    });
    await page.route('**/api/jobs/*', route => route.fulfill({ json: {
      id: model.id, status: 'complete', progress: 100, engine: 'meshy', model,
    } }));
    await page.goto('/');
    await page.getByLabel('创作方式', { exact: true }).selectOption('meshy');
    await page.getByLabel('你想做点什么？').fill('角色，高120毫米');
    // Produce a small valid raster locally; this tests the browser upload path.
    const raster = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 100; canvas.height = 160;
      const context = canvas.getContext('2d')!; context.fillStyle = '#b0a08f'; context.fillRect(0, 0, 100, 160);
      return canvas.toDataURL('image/png').split(',')[1];
    });
    await page.getByLabel('上传造型参考图', { exact: true }).setInputFiles({
      name: 'reference.png', mimeType: 'image/png', buffer: Buffer.from(raster, 'base64'),
    });
    await expect(page.getByAltText('造型参考图', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await page.screenshot({ path: `artifacts/reference-${width}.png`, fullPage: true });
    await page.getByRole('button', { name: '生成我的模型' }).click();
    await expect(page.locator('.generation-overlay')).toHaveCount(0);
    await expect(page.locator('.model-name h2')).toHaveText('参考图角色');
    expect(payloads).toHaveLength(1);
    expect(payloads[0].engine).toBe('meshy');
    expect(payloads[0].detail).toBe('fine');
    expect(payloads[0].reference).toMatch(/^data:image\/jpeg;base64,/);
    await page.getByRole('button', { name: '导出打印文件', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('打印待修复');
    await expect(page.getByRole('button', { name: '下载 3MF 文件', exact: true })).toBeDisabled();
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载原始形象（GLB）', exact: true }).click();
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toContain('原始形象.glb');
    expect(await fs.readFile((await download.path())!, 'utf8')).toBe('mock-original-GLB');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    expect(errors).toEqual([]);
  });
}

test('dedicated 3D key is entered independently and saved without exposing the existing key', async ({ page }) => {
  let saved: Record<string, unknown> | undefined;
  await page.route('**/api/settings', async route => {
    if (route.request().method() === 'PUT') saved = route.request().postDataJSON();
    await route.fulfill({ json: { enabled: true, base_url: 'https://example.com/v1', model: 'vision-model',
      has_key: true, has_meshy_key: Boolean(saved), meshy_texture: saved?.meshy_texture ?? true } });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: '生成我的模型' })).toBeEnabled();
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await expect(page.getByLabel('API 密钥', { exact: true })).toHaveValue('');
  await page.getByLabel('Meshy API 密钥', { exact: true }).fill('independent-test-key');
  await page.getByLabel('同时生成彩色材质', { exact: true }).uncheck();
  await page.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(saved?.meshy_api_key).toBe('independent-test-key');
  expect(saved?.api_key).toBe('');
  expect(saved?.meshy_texture).toBe(false);
});
