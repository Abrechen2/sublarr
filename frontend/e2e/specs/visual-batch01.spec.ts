/**
 * Visual verification for Batch 01 manual items
 * Captures screenshots for: active state, theme, language, ? shortcut, 404 back button
 */
import { test, expect } from '@playwright/test';

const OUT = 'e2e/visual-batch01';

test.describe('Visual Batch 01', () => {
  test('1.1.12 active sidebar link visual', async ({ page }) => {
    await page.goto('/library');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/1-1-12-active-sidebar.png`, fullPage: false });
  });

  test('1.2.1 dark mode visual', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/1-2-1-dark-mode.png` });
    // Click theme toggle
    const toggle = page.locator('button[aria-label*="Theme"], button[aria-label*="theme"], button[title*="dark"], button[title*="light"], button[title*="system"]').first();
    if (await toggle.isVisible()) {
      await toggle.click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/1-2-1-after-toggle.png` });
      await toggle.click(); // restore
    }
  });

  test('1.2.4 language switcher visual', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/1-2-4-lang-before.png` });
    const lang = page.locator('button[aria-label*="language"], button[aria-label*="Deutsch"], button[aria-label*="English"]').first();
    if (await lang.isVisible()) {
      const textBefore = await lang.innerText();
      await lang.click();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/1-2-4-lang-after.png` });
      const textAfter = await lang.innerText();
      // Store result as test annotation
      test.info().annotations.push({ type: 'lang-toggle', description: `${textBefore} → ${textAfter}` });
      expect(textAfter).not.toBe(textBefore); // flip happened
      await lang.click(); // restore
    }
  });

  test('1.3.3 ? shortcut modal via Shift+Slash', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    // Click on page body to ensure focus
    await page.mouse.click(400, 300);
    await page.waitForTimeout(200);
    await page.keyboard.press('Shift+/');
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/1-3-3-shortcut-modal.png` });
    const dialog = page.locator('[role="dialog"]').first();
    const isOpen = await dialog.isVisible().catch(() => false);
    test.info().annotations.push({ type: 'modal-open', description: String(isOpen) });
    // Close if open
    if (isOpen) await page.keyboard.press('Escape');
  });

  test('1.3.3b ? shortcut modal via keyboard.type', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await page.mouse.click(400, 300);
    await page.waitForTimeout(200);
    await page.keyboard.type('?');
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/1-3-3b-shortcut-type.png` });
  });

  test('1.4.1+1.4.2 404 page visual', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.goto('/this-route-does-not-exist');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/1-4-404-page.png` });
    // Look for any back-related element
    const bodyText = await page.locator('body').innerText();
    test.info().annotations.push({ type: 'body-text', description: bodyText.slice(0, 200) });
  });

  test('1.1.12 check active NavLink aria', async ({ page }) => {
    await page.goto('/library');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    // Check what attributes the active nav link actually has
    const navLink = page.locator('[data-testid="nav-link-library"]');
    const attrs = await navLink.evaluate((el) => {
      return {
        ariaCurrent: el.getAttribute('aria-current'),
        className: el.getAttribute('class'),
        style: el.getAttribute('style'),
      };
    });
    test.info().annotations.push({ type: 'nav-link-attrs', description: JSON.stringify(attrs) });
    await page.screenshot({ path: `${OUT}/1-1-12-nav-active-attrs.png` });
  });
});
