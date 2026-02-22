import { test, expect } from '@playwright/test';

/**
 * E2E tests for Onboarding Wizard
 * Tests the complete onboarding flow with all 5 steps
 */
test.describe('Onboarding Wizard', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to app (should redirect to onboarding if not configured)
    await page.goto('/');
  });

  test('should complete onboarding flow', async ({ page }) => {
    // Step 1: Welcome
    await expect(page.locator('text=Welcome to Sublarr')).toBeVisible();
    await page.click('button:has-text("Get Started")');

    // Step 2: Source Language
    await expect(page.locator('text=Source Language')).toBeVisible();
    await page.selectOption('select[name="sourceLanguage"]', 'en');
    await page.click('button:has-text("Next")');

    // Step 3: Target Language
    await expect(page.locator('text=Target Language')).toBeVisible();
    await page.selectOption('select[name="targetLanguage"]', 'de');
    await page.click('button:has-text("Next")');

    // Step 4: Ollama Configuration
    await expect(page.locator('text=Ollama Configuration')).toBeVisible();
    await page.fill('input[name="ollamaHost"]', 'http://localhost:11434');
    await page.fill('input[name="ollamaModel"]', 'llama3.1');
    await page.click('button:has-text("Next")');

    // Step 5: Media Server (optional)
    await expect(page.locator('text=Media Server')).toBeVisible();
    await page.click('button:has-text("Skip")'); // Optional step

    // Final: Complete
    await expect(page.locator('text=Setup Complete')).toBeVisible();
    await page.click('button:has-text("Finish")');

    // Should redirect to dashboard
    await expect(page).toHaveURL(/.*dashboard.*/);
  });

  test('should validate required fields', async ({ page }) => {
    await page.goto('/');
    await page.click('button:has-text("Get Started")');
    
    // Try to proceed without selecting source language
    await page.click('button:has-text("Next")');
    
    // Should show validation error
    await expect(page.locator('text=Please select a source language')).toBeVisible();
  });
});
