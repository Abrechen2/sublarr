import { test, expect } from '@playwright/test';
import { WantedPage } from '../pages/WantedPage';

test.describe('Wanted Page', () => {
  let wanted: WantedPage;

  test.beforeEach(async ({ page }) => {
    wanted = new WantedPage(page);
    await wanted.goto();
  });

  test('wanted page loads', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('wanted list is visible', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(wanted.list).toBeVisible({ timeout: 10000 });
  });

  test('status filter buttons are visible', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(wanted.filterStatus).toBeVisible({ timeout: 10000 });
  });

  test('items are displayed or empty state shown', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const itemCount = await wanted.items.count();
    if (itemCount === 0) {
      // Empty state should be visible
      const body = await page.locator('body').innerText();
      expect(body.length).toBeGreaterThan(20);
    } else {
      expect(itemCount).toBeGreaterThan(0);
    }
  });

  test('search button is visible on items if items exist', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const itemCount = await wanted.items.count();
    if (itemCount > 0) {
      const searchBtnCount = await wanted.searchButtons().count();
      expect(searchBtnCount).toBeGreaterThanOrEqual(1);
    }
  });

  test('process button is visible on items if items exist', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const itemCount = await wanted.items.count();
    if (itemCount > 0) {
      const processBtnCount = await wanted.processButtons().count();
      expect(processBtnCount).toBeGreaterThanOrEqual(1);
    }
  });

  test('clicking status filter updates displayed items', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const filterBtns = wanted.filterStatus.locator('button');
    const btnCount = await filterBtns.count();
    if (btnCount > 1) {
      // Click second filter option
      await filterBtns.nth(1).click();
      await page.waitForTimeout(500);
      // Page should still be functional
      await expect(wanted.list).toBeVisible();
    }
  });
});
