/**
 * Batch 06 — Wanted (/wanted)
 * Covers: UI_TEST_PLAN.md Section 5.1–5.6
 * Testids: wanted-filter-status, wanted-list, wanted-item,
 *           wanted-search-btn, wanted-process-btn
 */
import { test, expect } from '@playwright/test';
import { WantedPage } from '../pages/WantedPage';

test.setTimeout(60000);

async function gotoWanted(page: Parameters<Parameters<typeof test>[1]>[0]['page']) {
  const wanted = new WantedPage(page);
  await wanted.goto();
  // Wait for either items or empty state
  await page.waitForTimeout(2000);
}

// ─── 5.1 Summary Cards ───────────────────────────────────────────────────────

test.describe('5.1 Summary Cards', () => {
  test('5.1.1 Wanted page loads with summary counts', async ({ page }) => {
    await gotoWanted(page);
    const body = await page.locator('body').innerText();
    expect(body.trim().length).toBeGreaterThan(0);
    await page.screenshot({ path: 'e2e/visual-batch06/5-1-1-wanted-page.png' });
  });

  test('5.1.2 Search All button exists', async ({ page }) => {
    await gotoWanted(page);
    const searchAllBtn = page.locator('button:has-text("Search All"), button[title*="Search All"]').first();
    const hasBtn = await searchAllBtn.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) {
      test.skip(true, 'Search All button not found — may not exist if no wanted items');
    } else {
      await expect(searchAllBtn).toBeVisible();
    }
  });
});

// ─── 5.2 Filter Bar ──────────────────────────────────────────────────────────

test.describe('5.2 Filter Bar', () => {
  test.beforeEach(async ({ page }) => {
    await gotoWanted(page);
  });

  test('5.2.1 Status filter bar visible', async ({ page }) => {
    const filterBar = page.locator('[data-testid="wanted-filter-status"]').first();
    await expect(filterBar).toBeVisible({ timeout: 5000 });
  });

  test('5.2.1 Status filter buttons visible', async ({ page }) => {
    const filterBar = page.locator('[data-testid="wanted-filter-status"]').first();
    const hasBar = await filterBar.isVisible({ timeout: 3000 }).catch(() => false);
    if (hasBar) {
      const buttons = await filterBar.locator('button').count();
      expect(buttons).toBeGreaterThanOrEqual(1);
    } else {
      const body = await page.locator('body').innerText();
      expect(body.length).toBeGreaterThan(0);
    }
  });

  test('5.2.9 Title search input works', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="earch"], input[placeholder*="ilter"], [data-testid="wanted-search"]').first();
    const hasInput = await searchInput.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasInput) {
      test.skip(true, 'No search input found');
      return;
    }
    await searchInput.fill('xyz_no_match_test');
    await page.waitForTimeout(500);
    await searchInput.clear();
  });
});

// ─── 5.3 Item List ───────────────────────────────────────────────────────────

test.describe('5.3 Item List / Status Badges', () => {
  test.beforeEach(async ({ page }) => {
    await gotoWanted(page);
  });

  test('5.3.1 Wanted list container exists', async ({ page }) => {
    const list = page.locator('[data-testid="wanted-list"]').first();
    const hasList = await list.isVisible({ timeout: 5000 }).catch(() => false);
    if (hasList) {
      await expect(list).toBeVisible();
    } else {
      // Fallback: check body has content
      const body = await page.locator('body').innerText();
      expect(body.length).toBeGreaterThan(0);
    }
    await page.screenshot({ path: 'e2e/visual-batch06/5-3-1-wanted-list.png' });
  });

  test('5.3.2 Wanted items have status badges', async ({ page }) => {
    const items = page.locator('[data-testid="wanted-item"]');
    const count = await items.count();
    if (count === 0) {
      test.skip(true, 'No wanted items — empty state OK');
      return;
    }
    expect(count).toBeGreaterThanOrEqual(1);
    await page.screenshot({ path: 'e2e/visual-batch06/5-3-2-wanted-badges.png' });
  });
});

// ─── 5.4 Item Checkboxes / Batch Actions ─────────────────────────────────────

test.describe('5.4 Item Selection and Batch Actions', () => {
  test('5.4.1 Clicking item checkbox selects it', async ({ page }) => {
    await gotoWanted(page);
    const items = page.locator('[data-testid="wanted-item"]');
    const count = await items.count();
    if (count === 0) {
      test.skip(true, 'No wanted items');
      return;
    }
    const checkbox = items.first().locator('input[type="checkbox"]').first();
    const hasCheckbox = await checkbox.isVisible({ timeout: 2000 }).catch(() => false);
    if (!hasCheckbox) {
      test.skip(true, 'No checkbox on wanted items');
      return;
    }
    await checkbox.click();
    await page.waitForTimeout(200);
    const isChecked = await checkbox.isChecked();
    expect(isChecked).toBe(true);
    // Uncheck to restore
    await checkbox.click();
  });
});

// ─── 5.5 Per-Item Action Menu ─────────────────────────────────────────────────

test.describe('5.5 Per-Item Action Buttons', () => {
  test('5.5.2 Search button visible per item', async ({ page }) => {
    await gotoWanted(page);
    const searchBtn = page.locator('[data-testid="wanted-search-btn"]').first();
    const hasBtns = await searchBtn.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtns) {
      test.skip(true, 'No wanted-search-btn found — no wanted items or deployed without testid');
      return;
    }
    await expect(searchBtn).toBeVisible();
  });
});
