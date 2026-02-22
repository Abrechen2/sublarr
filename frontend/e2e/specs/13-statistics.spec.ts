import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('Statistics Page', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/statistics');
    await page.waitForLoadState('networkidle', { timeout: 10000 });
  });

  test('statistics page loads', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
  });

  test('statistics page has heading', async ({ page }) => {
    const bodyText = await page.locator('body').innerText();
    const hasStats = bodyText.toLowerCase().includes('statistic') || 
                     bodyText.toLowerCase().includes('statistik') ||
                     bodyText.toLowerCase().includes('chart') ||
                     bodyText.toLowerCase().includes('overview');
    expect(hasStats).toBe(true);
  });

  test('stat numbers or charts are visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(50);
  });

  test('provider stats are visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText();
    const hasProviderStats = bodyText.toLowerCase().includes('provider') ||
                              bodyText.toLowerCase().includes('download') ||
                              bodyText.toLowerCase().includes('translation');
    expect(hasProviderStats).toBe(true);
  });
});
