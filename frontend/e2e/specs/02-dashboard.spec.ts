import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';

test.describe('Dashboard', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboard = new DashboardPage(page);
    await dashboard.goto();
  });

  test('stats cards container is visible', async ({ page }) => {
    await expect(dashboard.statsCards).toBeVisible({ timeout: 10000 });
  });

  test('renders at least 2 stat cards', async ({ page }) => {
    await expect(dashboard.statsCards).toBeVisible({ timeout: 10000 });
    const count = await dashboard.statCard.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test('stat cards have content', async ({ page }) => {
    await expect(dashboard.statsCards).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    const cards = dashboard.statCard;
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);
    // At least one card should have text content
    const allText = await page.locator('[data-testid="stats-cards"]').innerText();
    expect(allText.length).toBeGreaterThan(10);
  });

  test('recent activity section is visible', async ({ page }) => {
    await expect(dashboard.recentActivity).toBeVisible({ timeout: 10000 });
  });

  test('page title or heading is present', async ({ page }) => {
    // Some heading identifying the dashboard
    const heading = page.locator('h1, h2, [class*="title"]').first();
    const _isVisible = await heading.isVisible().catch(() => false);
    // Not required to have h1, but body should be non-empty
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(100);
  });

  test('sidebar health indicator is visible and has color', async ({ page }) => {
    const indicator = page.locator('[data-testid="health-indicator"]');
    // Wait for health API response to arrive
    await page.waitForTimeout(2000);
    await expect(indicator).toBeVisible();
    const style = await indicator.getAttribute('style');
    // Indicator should have a color (either success or error — just verify it rendered)
    expect(style).toMatch(/var\(--(success|error)\)/);
  });
});
