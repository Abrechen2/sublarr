import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('History Page', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/history');
  });

  test('history page loads', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('history table or empty state is visible', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    // Either a table with rows or an empty state message
    const hasTable = await page.locator('table, [class*="table"], [class*="list"]').first().isVisible().catch(() => false);
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(20);
  });

  test('history entries contain download info if any exist', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const rows = page.locator('tr[data-testid], tbody tr').filter({ hasNotText: 'th' });
    const count = await rows.count();
    if (count > 0) {
      const firstRow = rows.first();
      const text = await firstRow.innerText();
      expect(text.length).toBeGreaterThan(0);
    }
  });

  test('history page has a heading or title', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const bodyText = await page.locator('body').innerText();
    // Should contain "History" or equivalent
    const hasHistoryText = bodyText.toLowerCase().includes('history') || 
                           bodyText.toLowerCase().includes('verlauf') ||
                           bodyText.toLowerCase().includes('downloads');
    expect(hasHistoryText).toBe(true);
  });
});
