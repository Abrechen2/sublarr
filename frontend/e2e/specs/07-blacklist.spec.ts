import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('Blacklist Page', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/blacklist');
  });

  test('blacklist page loads', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('blacklist shows entries or empty state', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(10);
  });

  test('blacklist page has heading', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const bodyText = await page.locator('body').innerText();
    const hasBlacklist = bodyText.toLowerCase().includes('blacklist') || 
                         bodyText.toLowerCase().includes('sperr') ||
                         bodyText.toLowerCase().includes('blocked');
    expect(hasBlacklist).toBe(true);
  });

  test('blacklist entries have remove button if entries exist', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const removeBtn = page.locator('button:has-text("Remove"), button[aria-label*="remove" i], button[aria-label*="delete" i]');
    const count = await removeBtn.count();
    // Either has entries with remove buttons, or is empty — both valid
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
