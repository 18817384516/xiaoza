import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import fs from 'node:fs/promises';

const generatedModels = new Map<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const ids: string[] = [];
  generatedModels.set(page, ids);
  page.on('response', async response => {
    if (response.url().endsWith('/api/generate') && response.request().method() === 'POST' && response.ok())
      ids.push((await response.json()).id);
  });
});
test.afterEach(async ({ page }) => {
  for (const id of generatedModels.get(page) || []) await page.request.delete('/api/models/' + id);
  generatedModels.delete(page);
});

async function open(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('button', { name: '生成我的模型' })).toBeEnabled({ timeout: 30000 });
}
async function create(page: Page, prompt: string) {
  await page.getByRole('button', { name: '新建作品', exact: true }).first().click();
  await page.getByLabel('创作方式', { exact: true }).selectOption('parametric');
  await page.getByLabel('你想做点什么？').fill(prompt);
  const request = page.waitForResponse(
    (r) => r.url().endsWith('/api/generate') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '生成我的模型' }).click();
  const id = (await (await request).json()).id;
  await expect
    .poll(
      async () => {
        const res = await page.request.get(`/api/jobs/${id}`);
        return (await res.json()).status;
      },
      { timeout: 90000 },
    )
    .toBe('complete');
  await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 15000 });
  await expect(page.locator('.error-banner')).toHaveCount(0);
  return id;
}

test('a complete beginner creates a dimensioned part, changes it, downloads it and restores a project', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await open(page);
  await create(page, '安装板，长80宽40厚5，4个孔，孔径5毫米');
  await expect(page.locator('.model-name h2')).toHaveText('安装板');
  await expect(page.getByLabel('宽度 / 外径', { exact: true })).toHaveValue('80');
  await expect(page.getByLabel('深度', { exact: true })).toHaveValue('40');
  await page.getByLabel('宽度 / 外径', { exact: true }).fill('90');
  await page.getByRole('button', { name: '应用修改' }).click();
  await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 30000 });
  await expect(page.getByLabel('宽度 / 外径', { exact: true })).toHaveValue('90');
  await page.getByLabel('观察方向').selectOption('top');
  await page.getByRole('button', { name: '雾霾蓝' }).click();
  await expect(page.getByRole('button', { name: '雾霾蓝' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: '导出打印文件' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  const filePromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载 3MF 文件' }).click();
  const download = await filePromise;
  expect(download.suggestedFilename()).toContain('.3mf');
  expect((await fs.stat((await download.path())!)).size).toBeGreaterThan(1000);
  const projectPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '同时备份可编辑项目（JSON）' }).click();
  const project = await projectPromise;
  const data = JSON.parse(await fs.readFile((await project.path())!, 'utf8'));
  expect(data.recipe.params.width).toBe(90);
  await page.getByRole('button', { name: '关闭弹窗' }).click();
  await page.getByRole('button', { name: '我的作品', exact: true }).click();
  await page.getByLabel('搜索作品').fill('安装板');
  await expect(page.locator('.library-card').first()).toBeVisible();
  await page.getByRole('button', { name: '新建作品', exact: true }).first().click();
  await expect(page.locator('.model-name h2')).toHaveText('你的下一件作品');
  await page
    .locator('input[accept=".json,application/json"]')
    .setInputFiles({
      name: 'project.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(data)),
    });
  await expect(page.locator('.model-name h2')).toHaveText('安装板', { timeout: 30000 });
  await expect(page.getByLabel('宽度 / 外径', { exact: true })).toHaveValue('90');
  expect(errors).toEqual([]);
});

test('draw a silhouette with a hole, extrude it and export real geometry', async ({ page }) => {
  await open(page);
  await page.getByRole('button', { name: '新建作品', exact: true }).first().click();
  await page.getByLabel('创作方式', { exact: true }).selectOption('parametric');
  await page.getByRole('tab', { name: '文字 + 草图' }).click();
  await page.getByRole('button', { name: '矩形', exact: true }).click();
  const canvas = page.getByLabel('草图画布，按住鼠标或手指绘制');
  const box = (await canvas.boundingBox())!;
  for (const [x1, y1, x2, y2] of [
    [0.12, 0.15, 0.85, 0.83],
    [0.35, 0.35, 0.55, 0.58],
  ]) {
    await page.mouse.move(box.x + box.width * x1, box.y + box.height * y1);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * x2, box.y + box.height * y2, { steps: 10 });
    await page.mouse.up();
  }
  await expect(page.locator('.sketch-count')).toContainText('2 个轮廓');
  await page.getByRole('button', { name: '使用这张草图' }).click();
  await page.getByLabel('你想做点什么？').fill('宽60毫米，高8毫米');
  const request = page.waitForResponse(
    (r) => r.url().endsWith('/api/generate') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '生成我的模型' }).click();
  const id = (await (await request).json()).id;
  await expect(page.locator('.model-name h2')).toHaveText('草图实体', { timeout: 30000 });
  const model = await (await page.request.get('/api/models/' + id)).json();
  expect(model.stats.watertight).toBe(true);
  expect(model.stats.components).toBe(1);
  expect(model.stats.dimensions[0]).toBe(60);
  expect(model.recipe.sketch.length).toBe(2);
  // A sketch-only project is valid even when no text was supplied.
  model.recipe.prompt = '';
  const importRequest = page.waitForResponse(
    (r) => r.url().endsWith('/api/generate') && r.request().method() === 'POST',
  );
  await page
    .locator('input[accept=".json,application/json"]')
    .setInputFiles({
      name: 'sketch-project.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(model)),
    });
  await importRequest;
  await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator('.error-banner')).toHaveCount(0);
  await expect(page.locator('.model-name h2')).toHaveText('草图实体');
  await page.screenshot({ path: 'artifacts/sketch-result.png', fullPage: true });
});

test('unsupported requests give clear recovery; animal revisions really rebuild the model', async ({
  page,
}) => {
  test.setTimeout(180000);
  await open(page);
  // History may restore the sketch from the previous test.
  await page.getByRole('tab', { name: '文字描述', exact: true }).click();
  await page.getByLabel('创作方式', { exact: true }).selectOption('parametric');
  await page.getByLabel('你想做点什么？').fill('复杂的喷气式飞机发动机');
  await page.getByRole('button', { name: '生成我的模型' }).click();
  await expect(page.getByRole('alert')).toContainText('当前本地模式', { timeout: 30000 });
  const id = await create(page, '一只圆滚滚的小兔，高65毫米，带底座');
  const before = await (await page.request.get('/api/models/' + id)).json();
  await page.getByRole('button', { name: '耳朵大一点', exact: true }).click();
  await expect(page.getByLabel('耳朵大小', { exact: true })).toHaveValue('1.15', {
    timeout: 30000,
  });
  await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 30000 });
  const models = await (await page.request.get('/api/models')).json();
  expect(models[0].stats.volume_cm3).not.toBe(before.stats.volume_cm3);
  expect(models[0].recipe.prompt).toBe(before.recipe.prompt);
  expect(models[0].recipe.edits).toContain('耳朵大一点');
  // Regenerating an unchanged idea keeps the revised dimensions.
  await page.getByRole('button', { name: '生成我的模型' }).click();
  await expect(page.locator('.generation-overlay')).toHaveCount(0, { timeout: 30000 });
  await expect(page.getByLabel('耳朵大小', { exact: true })).toHaveValue('1.15');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('选择你的创作方式');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('mobile has no overflow, preview controls work, and its guides stay readable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await create(page, '方块，长40宽30高20毫米');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole('button', { name: '显示或隐藏网格' }).click();
  await expect(page.getByRole('button', { name: '显示或隐藏网格' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await page.getByRole('button', { name: '使用指南', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await expect(page.getByRole('dialog')).toContainText('螺纹');
  await page.screenshot({ path: 'artifacts/help-mobile.png', fullPage: true });
  await page.getByRole('button', { name: '关闭弹窗' }).click();
  await page.getByRole('button', { name: '导出打印文件' }).click();
  await expect(page.getByRole('button', { name: '下载 3MF 文件' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

