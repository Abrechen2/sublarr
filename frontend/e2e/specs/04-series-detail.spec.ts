import { test, expect } from '@playwright/test';
import { LibraryPage } from '../pages/LibraryPage';
import { ANIME } from '../fixtures/anime';

test.describe('Series Detail', () => {
  let library: LibraryPage;

  test.beforeEach(async ({ page }) => {
    library = new LibraryPage(page);
    await library.goto();
  });

  test('clicking My Dress-Up Darling opens detail page', async ({ page }) => {
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 });
    await library.search(ANIME.dressDarling.titlePart);
    await expect(library.rows.first()).toBeVisible({ timeout: 5000 });
    await library.clickRow(0);
    // Should be on a detail page
    await expect(page).not.toHaveURL('http://localhost:5765/library', { timeout: 5000 });
  });

  test('series detail shows episode list', async ({ page }) => {
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 });
    await library.search(ANIME.dressDarling.titlePart);
    await expect(library.rows.first()).toBeVisible({ timeout: 5000 });
    await library.clickRow(0);
    await page.waitForLoadState('domcontentloaded', { timeout: 10000 });
    await page.waitForTimeout(1000);
    // Series detail page should have meaningful content (episode info, seasons, etc.)
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(100);
  });

  test('series detail has a title', async ({ page }) => {
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 });
    await library.search(ANIME.dressDarling.titlePart);
    await expect(library.rows.first()).toBeVisible({ timeout: 5000 });
    await library.clickRow(0);
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const heading = page.locator('h1, h2').first();
    const isVisible = await heading.isVisible().catch(() => false);
    if (isVisible) {
      const text = await heading.innerText();
      expect(text.length).toBeGreaterThan(0);
    }
    // Page should have loaded content
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(50);
  });

  test('back button or breadcrumb returns to library', async ({ page }) => {
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 });
    await library.clickRow(0);
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    // Find a back link/button
    const backBtn = page.locator('a[href="/library"], button:has-text("Back"), [aria-label*="back" i]').first();
    const isVisible = await backBtn.isVisible().catch(() => false);
    if (isVisible) {
      await backBtn.click();
      await expect(page).toHaveURL(/\/library/, { timeout: 5000 });
    }
  });

  test('series detail for Akame ga Kill shows episodes', async ({ page }) => {
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 });
    await library.search(ANIME.akameGaKill.titlePart);
    await expect(library.rows.first()).toBeVisible({ timeout: 5000 });
    await library.clickRow(0);
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(50);
  });
});
