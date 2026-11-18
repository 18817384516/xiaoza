import { test, expect } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`unsupported description recovery preserves the idea at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    await expect(page.getByRole('button', { name: '生成我的模型' })).toBeEnabled({ timeout: 30000 });
    await page.getByRole('button', { name: '新建作品', exact: true }).first().click();
    await page.getByLabel('创作方式', { exact: true }).selectOption('parametric');
    const idea = '复杂的喷气式飞机发动机';
    const input = page.getByLabel('你想做点什么？');
    await input.fill(idea);
    await page.getByRole('button', { name: '生成我的模型' }).click();
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('当前本地模式还做不了这个模型', { timeout: 30000 });
    await expect(input).toHaveValue(idea);
    await expect(alert).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);

    await alert.getByRole('button', { name: '查看可生成的模型' }).click();
    await expect(page.getByRole('dialog')).toContainText('本地可生成的模型');
    await expect(page.locator('.catalog-item')).toHaveCount(20);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await page.getByRole('button', { name: '保留描述，返回创作' }).click();
    await expect(input).toHaveValue(idea);

    await alert.getByRole('button', { name: '画轮廓并拉伸' }).click();
    await expect(page.getByRole('dialog')).toContainText('画下来，就能做出来');
    await page.keyboard.press('Escape');
    await expect(input).toHaveValue(idea);
    await alert.getByRole('button', { name: '连接 AI', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('选择你的创作方式');
    await page.keyboard.press('Escape');
    await expect(input).toHaveValue(idea);
    await page.screenshot({ path: `artifacts/recovery-${width}.png`, fullPage: true });

    await alert.getByRole('button', { name: '改用自由创造', exact: true }).click();
    await expect(page.getByLabel('创作方式', { exact: true })).toHaveValue('blender');
    await expect(input).toHaveValue(idea);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.getByLabel('创作方式', { exact: true }).selectOption('parametric');
    await page.getByRole('button', { name: '生成我的模型' }).click();
    await expect(alert).toContainText('当前本地模式', { timeout: 30000 });

    await alert.getByRole('button', { name: '查看可生成的模型' }).click();
    await page.getByRole('button', { name: '圆形垫片 填入示例' }).click();
    await expect(input).toHaveValue('圆形垫片');
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator('.generation-overlay')).toHaveCount(0);
  });
}
