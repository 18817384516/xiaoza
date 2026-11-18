import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

for (const errorCode of ['blender_ai_connection', 'blender_ai_timeout', 'blender_validation_failed']) {
  test(`connection recovery continues the failed job without losing the idea: ${errorCode}`, async ({ page }) => {
    const sample = JSON.parse(await fs.readFile('examples/牛油果椅子.json', 'utf8'));
    const failedId = 'd'.repeat(32);
    const resumedId = 'e'.repeat(32);
    const submitted: Record<string, unknown>[] = [];
    await page.route('**/api/generate', async route => {
      submitted.push(route.request().postDataJSON());
      await route.fulfill({ status: 202, json: { id: submitted.length === 1 ? failedId : resumedId } });
    });
    await page.route(`**/api/jobs/${failedId}`, route => route.fulfill({ json: {
      id: failedId, engine: 'blender', status: 'error', progress: 35,
      stage: '大模型正在修正建模步骤', error_code: errorCode,
      error: '大模型连接中断，建模步骤已保留，可点击继续重试。',
    } }));
    await page.route(`**/api/jobs/${resumedId}`, route => route.fulfill({ json: {
      id: resumedId, engine: 'blender', status: 'complete', progress: 100,
      stage: '模型已就绪', model: sample,
    } }));
    await page.goto('/');
    await expect(page.getByRole('button', { name: '生成我的模型' })).toBeEnabled();
    await page.getByRole('button', { name: '新建作品', exact: true }).first().click();
    const prompt = page.getByLabel('你想做点什么？');
    await prompt.fill(sample.recipe.prompt);
    await page.getByRole('button', { name: '生成我的模型' }).click();
    await expect(page.getByRole('alert')).toContainText('建模步骤已保留');
    await expect(prompt).toHaveValue(sample.recipe.prompt);
    await page.getByRole('button', { name: errorCode === 'blender_validation_failed' ? '继续修复' : '继续重试', exact: true }).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator('.generation-overlay')).toHaveCount(0);
    await expect(page.locator('.model-name h2')).toHaveText(sample.name);
    expect(submitted).toHaveLength(2);
    expect(submitted[1].resume_job).toBe(failedId);
    await expect(prompt).toHaveValue(sample.recipe.prompt);
  });
}
