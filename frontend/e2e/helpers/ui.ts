import { Page, expect } from '@playwright/test';

/** Wait for the app to finish loading (spinner gone, main content visible) */
export async function waitForAppReady(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout: 15000 });
}

/** Wait for a toast notification to appear and optionally match text */
export async function waitForToast(page: Page, text?: string): Promise<void> {
  const toast = page.locator('[data-testid="toast"]').first();
  await expect(toast).toBeVisible({ timeout: 10000 });
  if (text) {
    await expect(toast).toContainText(text);
  }
}

/** Wait for an API call to complete by watching network */
export async function waitForApi(page: Page, urlPattern: string | RegExp): Promise<void> {
  await page.waitForResponse(
    (resp) => {
      const url = resp.url();
      if (typeof urlPattern === 'string') return url.includes(urlPattern);
      return urlPattern.test(url);
    },
    { timeout: 15000 }
  );
}

/** Assert a status badge has the expected color class or text */
export async function expectBadge(
  page: Page,
  selector: string,
  expectedText: string
): Promise<void> {
  const badge = page.locator(selector).first();
  await expect(badge).toBeVisible();
  await expect(badge).toContainText(expectedText);
}

/** Fill a search input and wait for results to update */
export async function searchIn(page: Page, inputSelector: string, query: string): Promise<void> {
  const input = page.locator(inputSelector);
  await input.clear();
  await input.fill(query);
  // Small debounce wait
  await page.waitForTimeout(400);
}

/** Navigate to a page via sidebar link */
export async function navigateTo(page: Page, linkText: string): Promise<void> {
  await page.locator(`[data-testid="sidebar"] a`, { hasText: linkText }).click();
  await waitForAppReady(page);
}
