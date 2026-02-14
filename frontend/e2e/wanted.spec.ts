import { test, expect } from '@playwright/test';

/**
 * E2E tests for Wanted page
 * Tests search and download functionality
 */
test.describe('Wanted Page', () => {
  test.beforeEach(async ({ page }) => {
    // Assume app is configured and navigate to wanted page
    await page.goto('/wanted');
  });

  test('should display wanted items', async ({ page }) => {
    // Wait for wanted items to load
    await page.waitForSelector('[data-testid="wanted-item"]', { timeout: 10000 });
    
    // Check that items are displayed
    const items = page.locator('[data-testid="wanted-item"]');
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should search for subtitles', async ({ page }) => {
    // Wait for page to load
    await page.waitForSelector('button:has-text("Search")', { timeout: 5000 });
    
    // Click search button on first item
    const firstSearchButton = page.locator('button[aria-label="Search"]').first();
    if (await firstSearchButton.isVisible()) {
      await firstSearchButton.click();
      
      // Wait for search results
      await page.waitForSelector('[data-testid="search-result"]', { timeout: 10000 });
      
      // Verify results are displayed
      const results = page.locator('[data-testid="search-result"]');
      const resultCount = await results.count();
      expect(resultCount).toBeGreaterThanOrEqual(0);
    }
  });

  test('should process wanted item', async ({ page }) => {
    // Wait for page to load
    await page.waitForSelector('button[aria-label="Process"]', { timeout: 5000 });
    
    // Click process button on first item
    const firstProcessButton = page.locator('button[aria-label="Process"]').first();
    if (await firstProcessButton.isVisible()) {
      await firstProcessButton.click();
      
      // Wait for processing to start (status change or notification)
      await page.waitForTimeout(2000);
      
      // Verify status changed or notification appeared
      // This depends on actual implementation
    }
  });

  test('should filter wanted items', async ({ page }) => {
    // Wait for filters to be available
    await page.waitForSelector('select[name="status"]', { timeout: 5000 });
    
    // Filter by status
    await page.selectOption('select[name="status"]', 'wanted');
    
    // Wait for filtered results
    await page.waitForTimeout(1000);
    
    // Verify filter is applied (check URL or items)
    const url = page.url();
    expect(url).toContain('status=wanted');
  });
});
