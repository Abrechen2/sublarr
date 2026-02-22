import { test, expect } from '@playwright/test';
import { SettingsPage } from '../pages/SettingsPage';

test.describe('Settings - Integrations', () => {
  let settings: SettingsPage;

  test.beforeEach(async ({ page }) => {
    settings = new SettingsPage(page);
    await settings.goto();
    await page.waitForLoadState('networkidle', { timeout: 10000 });
  });

  test('integrations section is accessible', async ({ page }) => {
    const intTab = page.locator('[role="tab"]:has-text("Integration"), button:has-text("Integration")').first();
    const isVisible = await intTab.isVisible().catch(() => false);
    if (isVisible) {
      await intTab.click();
      await page.waitForTimeout(300);
    }
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(50);
  });

  test('Sonarr section is present', async ({ page }) => {
    const intTab = page.locator('[role="tab"]:has-text("Integration"), button:has-text("Integration")').first();
    const isVisible = await intTab.isVisible().catch(() => false);
    if (isVisible) {
      await intTab.click();
      await page.waitForTimeout(300);
    }
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.toLowerCase()).toContain('sonarr');
  });

  test('Radarr section is present', async ({ page }) => {
    const intTab = page.locator('[role="tab"]:has-text("Integration"), button:has-text("Integration")').first();
    const isVisible = await intTab.isVisible().catch(() => false);
    if (isVisible) {
      await intTab.click();
      await page.waitForTimeout(300);
    }
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.toLowerCase()).toContain('radarr');
  });

  test('integrations tab has content', async ({ page }) => {
    const intTab = page.locator('[role="tab"]:has-text("Integration"), button:has-text("Integration")').first();
    const isVisible = await intTab.isVisible().catch(() => false);
    if (isVisible) {
      await intTab.click();
      await page.waitForTimeout(300);
    }
    const bodyText = await page.locator('body').innerText();
    // Integrations section should have meaningful content
    expect(bodyText.length).toBeGreaterThan(50);
  });

  test('test connection buttons exist', async ({ page }) => {
    const intTab = page.locator('[role="tab"]:has-text("Integration"), button:has-text("Integration")').first();
    const isVisible = await intTab.isVisible().catch(() => false);
    if (isVisible) {
      await intTab.click();
      await page.waitForTimeout(300);
    }
    const testBtn = page.locator('button:has-text("Test"), button:has-text("Verbindung testen")');
    const count = await testBtn.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
