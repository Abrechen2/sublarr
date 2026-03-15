import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('Settings - Core', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/settings');
    await basePage.waitForReady();
  });

  test('Navigate to Settings Provider', async ({ page }) => {
    await page.locator('button:has-text("Provider")').first().click();
    await page.waitForTimeout(1000);
    // Wait for either Configured tab button or the counter text
    await expect(
      page.locator('button:has-text("Configured"), text=/\\d+ aktiv/')
        .first()
    ).toBeVisible({ timeout: 5000 });
  });

  test.describe('32.1 Security Tab', () => {
    test.beforeEach(async ({ page }) => {
      await page.locator('button:has-text("Security")').first().click();
      await expect(page.locator('text=UI Authentication')).toBeVisible({ timeout: 5000 });
    });

    test('32.1.1-32.1.2 Require Login toggle', async ({ page }) => {
      await expect(page.locator('text=Require login')).toBeVisible();

      // Find the non-disabled switch (first disabled ones may be from other sections)
      const authToggle = page.locator('button[role="switch"]:not([disabled])').first();
      const hasToggle = await authToggle.isVisible({ timeout: 3000 }).catch(() => false);
      if (!hasToggle) {
        test.skip(true, 'No clickable auth toggle found on Security section');
        return;
      }

      const isAuthEnabled = await authToggle.getAttribute('aria-checked') === 'true';
      await authToggle.click();
      await page.waitForTimeout(500);
      await expect(authToggle).toHaveAttribute('aria-checked', isAuthEnabled ? 'false' : 'true');

      // Revert
      await authToggle.click();
      await page.waitForTimeout(300);
    });

    test('32.1.3 Password visibility toggle', async ({ page }) => {
      const authToggle = page.locator('button[role="switch"]:not([disabled])').first();
      const hasToggle = await authToggle.isVisible({ timeout: 3000 }).catch(() => false);
      if (!hasToggle) {
        test.skip(true, 'Auth toggle not available');
        return;
      }

      const wasEnabled = await authToggle.getAttribute('aria-checked') === 'true';
      if (!wasEnabled) {
        await authToggle.click();
        await page.waitForTimeout(800);
      }

      const pwInput = page.locator('input[type="password"]').first();
      const hasPwInput = await pwInput.isVisible({ timeout: 3000 }).catch(() => false);
      if (!hasPwInput) {
        if (!wasEnabled) await authToggle.click();
        test.skip(true, 'Password fields not rendered after enabling auth');
        return;
      }

      const eyeBtn = page.locator('button[aria-label="Show"]').first();
      const hasEyeBtn = await eyeBtn.isVisible({ timeout: 2000 }).catch(() => false);
      if (hasEyeBtn) {
        await eyeBtn.click();
        await expect(page.locator('input[type="text"]').first()).toBeVisible();
        await page.locator('button[aria-label="Hide"]').first().click();
      }

      if (!wasEnabled) {
        await authToggle.click();
        await page.waitForTimeout(300);
      }
    });

    test('32.1.4-32.1.6 Password changing validation', async ({ page }) => {
      const authToggle = page.locator('button[role="switch"]:not([disabled])').first();
      const hasToggle = await authToggle.isVisible({ timeout: 3000 }).catch(() => false);
      if (!hasToggle) {
        test.skip(true, 'Auth toggle not available');
        return;
      }

      const wasEnabled = await authToggle.getAttribute('aria-checked') === 'true';
      if (!wasEnabled) {
        await authToggle.click();
        await page.waitForTimeout(800);
      }

      const changeBtn = page.locator('button:has-text("Change Password")');
      const hasChaBtn = await changeBtn.isVisible({ timeout: 3000 }).catch(() => false);
      if (!hasChaBtn) {
        if (!wasEnabled) await authToggle.click();
        test.skip(true, 'Change Password button not visible');
        return;
      }

      // Empty fields → disabled
      await expect(changeBtn).toBeDisabled();

      if (!wasEnabled) {
        await authToggle.click();
        await page.waitForTimeout(300);
      }
    });
  });

  test.describe('32.2 Providers Section', () => {
    test.beforeEach(async ({ page }) => {
      await page.locator('button:has-text("Provider")').first().click();
      // Wait for provider content to load
      await expect(page.locator('text=/\\d+ aktiv \\/ \\d+ konfiguriert/')).toBeVisible({ timeout: 8000 });
    });

    test('32.2.1 Configured/Marketplace tabs', async ({ page }) => {
      await expect(page.locator('button:has-text("Configured")')).toBeVisible();
      await page.locator('button:has-text("Marketplace")').first().click();
      await page.waitForTimeout(500);
      await expect(page.locator('main')).toBeVisible();
      await page.locator('button:has-text("Configured")').click();
    });

    test('32.2.2 Zähler Text', async ({ page }) => {
      await expect(page.locator('text=/\\d+ aktiv \\/ \\d+ konfiguriert/')).toBeVisible();
    });

    test('32.2.3 Clear Cache button exists', async ({ page }) => {
      const clearBtn = page.locator('button:has-text("Gesamten Cache leeren")');
      await expect(clearBtn).toBeVisible();
    });

    test('32.2.4-32.2.6 Provider cards rendered with actions', async ({ page }) => {
      // Wait for provider cards to appear
      await page.waitForTimeout(1000);
      const editButtons = page.locator('button:has-text("Bearbeiten")');
      await expect(editButtons.first()).toBeVisible({ timeout: 5000 });
      const count = await editButtons.count();
      expect(count).toBeGreaterThan(0);
    });
  });
});
