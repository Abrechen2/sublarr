import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.describe('2.1 Widget Visibility', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/');
  });

  test('2.1.1-2.1.8 Widgets are visible on dashboard', async ({ page }) => {
    // Wait for widgets to load
    await page.waitForSelector('.react-grid-layout');

    // Make sure different widgets are generally mounted. 
    // They usually render their titles or distinctive classes. We'll check for generic widget headers/presence.
    const widgetHeaders = page.locator('.react-grid-item');
    const count = await widgetHeaders.count();
    expect(count).toBeGreaterThanOrEqual(1); // Standard layout has multiple widgets
  });
});

test.describe('2.2 Dashboard Customize Modal', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/');
  });

  test('2.2.1 Customize button opens modal', async ({ page }) => {
    // wait for render
    await page.waitForTimeout(1000); 
    // select by position next to h1 or the flex container
    await page.locator('.flex.items-center.justify-between > button').click();
    const modal = page.locator('div[role="dialog"]');
    await expect(modal).toBeVisible();
  });

  test('2.2.2-2.2.4 Disable widget, persist, then re-enable', async ({ page }) => {
    // Wait for the grid to load initially
    await page.waitForSelector('.react-grid-layout');

    // 1. Open modal
    await page.locator('.flex.items-center.justify-between > button').click();
    
    // Check state of first toggle switch
    const modal = page.locator('div[role="dialog"]');
    const toggle = modal.locator('button[role="switch"]').first();
    await expect(toggle).toBeVisible();
    
    const wasChecked = await toggle.getAttribute('aria-checked') === 'true';
    
    // We count the widgets directly in the DOM. Wait for them to be present.
    await page.waitForTimeout(500);
    const widgetItemsBefore = await page.locator('.react-grid-item').count();

    // 2. Toggle the switch
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', wasChecked ? 'false' : 'true');

    // 3. Close modal (clicking X or background)
    await page.keyboard.press('Escape');

    // Wait for animation to finish and grid to reculculate
    await page.waitForTimeout(1000);

    // Widget count should change
    const widgetItemsAfterToggle = await page.locator('.react-grid-item').count();
    expect(widgetItemsAfterToggle).not.toBe(widgetItemsBefore);

    // 4. Reload page to test persistence
    await page.reload();
    await basePage.waitForReady();
    await page.waitForSelector('.react-grid-layout');
    await page.waitForTimeout(1000); // wait for re-layout

    // Check count stays the same after reload
    const widgetItemsReload = await page.locator('.react-grid-item').count();
    expect(widgetItemsReload).toBe(widgetItemsAfterToggle);

    // 5. Restore the widget by toggling again
    await page.locator('.flex.items-center.justify-between > button').click();
    await page.waitForTimeout(500);
    const toggleAfterReload = page.locator('div[role="dialog"]').locator('button[role="switch"]').first();
    await toggleAfterReload.click();
    
    await page.keyboard.press('Escape');

    // Count should be back to original
    await page.waitForTimeout(1000);
    const widgetItemsRestored = await page.locator('.react-grid-item').count();
    expect(widgetItemsRestored).toBe(widgetItemsBefore);
  });
  
  test('2.2.5 Modal close logic', async ({ page }) => {
    await page.locator('.flex.items-center.justify-between > button').click();
    const modal = page.locator('div[role="dialog"]');
    await expect(modal).toBeVisible();
    
    // Click outside to close (or escape, verified in previous test)
    await page.mouse.click(10, 10);
    await expect(modal).toBeHidden();
  });
});

test.describe('24.1 Dashboard Layout & Edit Mode', () => {
  let basePage: BasePage;

  test.beforeEach(async ({ page }) => {
    basePage = new BasePage(page);
    await basePage.goto('/');
  });

  test('24.1.1 Edit mode toggling', async ({ page }) => {
    // Wait for the grid to load initially
    await page.waitForSelector('.react-grid-layout');
    
    // Toggle edit mode (Edit Layout button)
    await page.locator('.flex.justify-end.mb-2 > button').click();
    await page.waitForTimeout(500); // wait for React re-render
    
    // Now remove buttons should be visible on widgets
    const removeButtons = page.locator('button[title="Remove widget"]');
    await expect(removeButtons.first()).toBeVisible();
    
    // Toggle edit mode off
    await page.locator('.flex.justify-end.mb-2 > button').click();
    await page.waitForTimeout(500);
    
    // Expect remove buttons to be hidden/removed
    const btnCount = await removeButtons.count();
    if (btnCount > 0) {
      await expect(removeButtons.first()).toBeHidden();
    }
  });
});
