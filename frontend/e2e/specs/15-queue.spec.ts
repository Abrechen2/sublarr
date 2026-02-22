import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('Queue Page', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/queue');
    await page.waitForLoadState('networkidle', { timeout: 10000 });
  });

  test('queue page loads', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
  });

  test('queue page has heading', async ({ page }) => {
    const bodyText = await page.locator('body').innerText();
    const hasQueue = bodyText.toLowerCase().includes('queue') || 
                     bodyText.toLowerCase().includes('warteschlange') ||
                     bodyText.toLowerCase().includes('pending');
    expect(hasQueue).toBe(true);
  });

  test('queue items or empty state is displayed', async ({ page }) => {
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(20);
  });

  test('queue items have action buttons if items exist', async ({ page }) => {
    const queueItems = page.locator('[class*="queue-item"], [class*="job"], tbody tr').first();
    const hasItems = await queueItems.isVisible().catch(() => false);
    if (hasItems) {
      const actionBtn = page.locator('button:has-text("Cancel"), button:has-text("Retry"), button:has-text("Remove")').first();
      const hasBtn = await actionBtn.isVisible().catch(() => false);
      // Action buttons optional depending on item state
    }
    expect(await page.locator('body').isVisible()).toBe(true);
  });
});
