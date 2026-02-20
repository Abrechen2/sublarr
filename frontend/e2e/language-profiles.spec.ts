import { test, expect } from '@playwright/test';

/**
 * E2E tests for Language Profile management
 */
test.describe('Language Profiles', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
    await page.click('button:has-text("Language Profiles")');
  });

  test('should create language profile', async ({ page }) => {
    // Click create button
    await page.click('button:has-text("Create Profile")');
    
    // Fill in profile details
    await page.fill('input[name="name"]', 'Test Profile');
    await page.selectOption('select[name="languages"]', 'de');
    await page.fill('input[name="minScore"]', '200');
    await page.check('input[name="preferAss"]');
    
    // Save profile
    await page.click('button:has-text("Save")');
    
    // Wait for profile to appear in list
    await page.waitForSelector('text=Test Profile', { timeout: 5000 });
    
    // Verify profile was created
    await expect(page.locator('text=Test Profile')).toBeVisible();
  });

  test('should edit language profile', async ({ page }) => {
    // Wait for profiles to load
    await page.waitForSelector('[data-testid="language-profile"]', { timeout: 5000 });
    
    // Click edit on first profile
    const editButton = page.locator('button[aria-label="Edit"]').first();
    if (await editButton.isVisible()) {
      await editButton.click();
      
      // Modify profile
      await page.fill('input[name="name"]', 'Updated Profile');
      
      // Save
      await page.click('button:has-text("Save")');
      
      // Verify update
      await expect(page.locator('text=Updated Profile')).toBeVisible();
    }
  });

  test('should delete language profile', async ({ page }) => {
    // Wait for profiles
    await page.waitForSelector('[data-testid="language-profile"]', { timeout: 5000 });
    
    // Click delete on first profile
    const deleteButton = page.locator('button[aria-label="Delete"]').first();
    if (await deleteButton.isVisible()) {
      await deleteButton.click();
      
      // Confirm deletion
      await page.click('button:has-text("Confirm")');
      
      // Wait for profile to be removed
      await page.waitForTimeout(1000);
    }
  });
});
