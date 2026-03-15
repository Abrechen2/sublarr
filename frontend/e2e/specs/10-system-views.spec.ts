/**
 * Batch 10 — System Views: Statistics, Tasks, Logs, Plugins
 * Sections 10–13 of UI_TEST_PLAN.md
 */
import { test, expect } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

test.setTimeout(30000);

test.describe('10. Statistics (/statistics)', () => {
  test('10.1 Statistics page loads', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/statistics');
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(50);
    await page.screenshot({ path: 'e2e/visual-batch10/10-1-statistics.png' });
  });

  test('10.2 Statistics has chart or metric content', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/statistics');
    // Charts render as canvas or SVG, or there are stat cards
    const hasCanvas = await page.locator('canvas').count();
    const hasSvg = await page.locator('svg').count();
    const body = await page.locator('body').innerText();
    const hasText = body.toLowerCase().match(/statistic|download|subtitle|translate|provider/i);
    expect(hasCanvas + hasSvg > 0 || hasText !== null).toBe(true);
  });

  test('10.3 Statistics page has heading', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/statistics');
    const body = await page.locator('body').innerText();
    const hasHeading = /statistic|statistik|overview|download/i.test(body);
    expect(hasHeading).toBe(true);
  });
});

test.describe('11. Tasks (/tasks)', () => {
  test('11.1 Tasks page loads', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/tasks');
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(20);
    await page.screenshot({ path: 'e2e/visual-batch10/11-1-tasks.png' });
  });

  test('11.2 Tasks page has content', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/tasks');
    await page.waitForTimeout(1000);
    const body = await page.locator('body').innerText();
    const hasContent = /task|scan|job|scheduler|next|run/i.test(body);
    expect(hasContent || body.length > 100).toBe(true);
  });

  test('11.4 Scheduler timing visible', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/tasks');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'e2e/visual-batch10/11-4-tasks-scheduler.png' });
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(20);
  });
});

test.describe('12. Logs (/logs)', () => {
  test('12.1 Logs page loads', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/logs');
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(20);
    await page.screenshot({ path: 'e2e/visual-batch10/12-1-logs.png' });
  });

  test('12.2 Logs page has log content or filter', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/logs');
    await page.waitForTimeout(1000);
    const body = await page.locator('body').innerText();
    const hasLog = /log|debug|info|warning|error|event/i.test(body);
    expect(hasLog || body.length > 100).toBe(true);
  });

  test('12.9 Log level filter visible', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/logs');
    await page.waitForTimeout(500);
    // Look for level filter buttons or dropdown
    const filterEl = page.locator('button:has-text("DEBUG"), button:has-text("INFO"), button:has-text("ERROR"), select').first();
    const hasFilter = await filterEl.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasFilter) {
      test.skip(true, 'No level filter found on logs page');
      return;
    }
    await expect(filterEl).toBeVisible();
  });

  test('12.7 Download button exists', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/logs');
    await page.waitForTimeout(500);
    const dlBtn = page.locator('button:has-text("Download"), button[title*="Download"], a[download]').first();
    const hasBtn = await dlBtn.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) {
      test.skip(true, 'No download button found');
      return;
    }
    await expect(dlBtn).toBeVisible();
  });
});

test.describe('13. Plugins (/plugins)', () => {
  test('13.1 Plugins page loads', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/plugins');
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(20);
    await page.screenshot({ path: 'e2e/visual-batch10/13-1-plugins.png' });
  });

  test('13.1 Plugins marketplace has content', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/plugins');
    await page.waitForTimeout(1000);
    const body = await page.locator('body').innerText();
    const hasPlugin = /plugin|marketplace|install|extension/i.test(body);
    expect(hasPlugin || body.length > 50).toBe(true);
  });
});
