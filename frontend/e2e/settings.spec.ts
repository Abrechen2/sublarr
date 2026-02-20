import { test, expect } from '@playwright/test';

/**
 * E2E tests for Settings page
 * Tests configuration and provider management
 */
test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('should display settings tabs', async ({ page }) => {
    // Check that settings tabs are visible
    await expect(page.locator('button:has-text("General")')).toBeVisible();
    await expect(page.locator('button:has-text("Providers")')).toBeVisible();
    await expect(page.locator('button:has-text("Translation")')).toBeVisible();
  });

  test('should configure provider', async ({ page }) => {
    // Navigate to Providers tab
    await page.click('button:has-text("Providers")');
    
    // Wait for providers list
    await page.waitForSelector('[data-testid="provider-item"]', { timeout: 5000 });
    
    // Enable a provider (if not already enabled)
    const providerToggle = page.locator('input[type="checkbox"][data-testid="provider-enabled"]').first();
    if (await providerToggle.isVisible()) {
      await providerToggle.click();
      
      // Wait for save
      await page.waitForTimeout(1000);
      
      // Verify provider is enabled
      await expect(providerToggle).toBeChecked();
    }
  });

  test('should test provider connection', async ({ page }) => {
    // Navigate to Providers tab
    await page.click('button:has-text("Providers")');
    
    // Wait for providers
    await page.waitForSelector('button:has-text("Test")', { timeout: 5000 });
    
    // Click test button
    const testButton = page.locator('button:has-text("Test")').first();
    if (await testButton.isVisible()) {
      await testButton.click();
      
      // Wait for test result
      await page.waitForSelector('[data-testid="provider-test-result"]', { timeout: 10000 });
      
      // Verify result is displayed
      const result = page.locator('[data-testid="provider-test-result"]');
      await expect(result).toBeVisible();
    }
  });

  test('should save settings', async ({ page }) => {
    // Make a change (e.g., update source language)
    await page.selectOption('select[name="sourceLanguage"]', 'ja');
    
    // Click save button
    await page.click('button:has-text("Save")');
    
    // Wait for success message
    await page.waitForSelector('text=Settings saved', { timeout: 5000 });
    
    // Verify success
    await expect(page.locator('text=Settings saved')).toBeVisible();
  });
});
