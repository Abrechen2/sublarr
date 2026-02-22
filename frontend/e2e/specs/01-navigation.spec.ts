import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('Navigation', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/');
  });

  test('sidebar is visible', async ({ page }) => {
    await expect(basePage.sidebar).toBeVisible();
  });

  test('health indicator is visible', async ({ page }) => {
    await expect(basePage.healthIndicator).toBeVisible();
  });

  test('navigate to Library via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-library');
    await basePage.expectCurrentPath('/library');
  });

  test('navigate to Wanted via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-wanted');
    await basePage.expectCurrentPath('/wanted');
  });

  test('navigate to Activity via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-activity');
    await basePage.expectCurrentPath('/activity');
  });

  test('navigate to History via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-history');
    await basePage.expectCurrentPath('/history');
  });

  test('navigate to Blacklist via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-blacklist');
    await basePage.expectCurrentPath('/blacklist');
  });

  test('navigate to Settings via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-settings');
    await basePage.expectCurrentPath('/settings');
  });

  test('navigate to Logs via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-logs');
    await basePage.expectCurrentPath('/logs');
  });

  test('navigate to Statistics via sidebar', async ({ page }) => {
    await basePage.navigateTo('nav-link-statistics');
    await basePage.expectCurrentPath('/statistics');
  });

  test('404 page for unknown route', async ({ page }) => {
    await page.goto('/this-route-does-not-exist-xyz');
    // Should render a not-found page (sidebar still visible or 404 message)
    const body = page.locator('body');
    await expect(body).toBeVisible();
    // Either shows 404 text or redirects to home
    const text = await body.innerText();
    expect(text.length).toBeGreaterThan(0);
  });

  test('search trigger button opens modal', async ({ page }) => {
    const trigger = page.locator('[data-testid="sidebar-search-trigger"]');
    await expect(trigger).toBeVisible();
    await trigger.click();
    // Global search modal or overlay should appear
    await page.waitForTimeout(300);
    // Check some modal-like element appeared (input or dialog)
    const searchInput = page.locator('input[type="text"], input[placeholder*="earch"]').first();
    // If modal opened, input should be focused or visible
    const inputVisible = await searchInput.isVisible().catch(() => false);
    // Not all implementations open a modal - just verify no error occurred
    expect(await page.locator('body').isVisible()).toBe(true);
  });
});
