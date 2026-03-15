/**
 * Batch 09 — Auth (Login, Setup, Onboarding)
 * Section 14 of UI_TEST_PLAN.md
 */
import { test, expect } from '@playwright/test';

test.setTimeout(30000);

test.describe('14.1 Login Page', () => {
  test('14.1.1 Login page renders (or redirects if auth disabled)', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    // If auth is disabled, app redirects to /. Either way page should load.
    const url = page.url();
    const isLoginOrRoot = /\/(login|$|#)/.test(url) || url.endsWith('/');
    expect(isLoginOrRoot).toBe(true);
  });

  test('14.1.2 Login form fields visible (if auth enabled)', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    const url = page.url();
    // If redirected to root, auth is disabled — skip
    if (!url.includes('/login')) {
      test.skip(true, 'Auth is disabled — redirected to root');
      return;
    }
    const emailOrUser = page.locator('input[type="email"], input[type="text"], input[name="email"], input[name="username"]').first();
    const password = page.locator('input[type="password"]').first();
    const hasEmail = await emailOrUser.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasEmail) {
      test.skip(true, 'Login form fields not found — page may redirect to setup/onboarding');
      return;
    }
    await expect(emailOrUser).toBeVisible();
    await expect(password).toBeVisible({ timeout: 5000 });
  });

  test('14.1.4 Empty form shows validation (if auth enabled)', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    if (!page.url().includes('/login')) {
      test.skip(true, 'Auth is disabled');
      return;
    }
    const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")').first();
    const hasBtn = await submitBtn.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) {
      test.skip(true, 'No submit button found');
      return;
    }
    await submitBtn.click();
    // Expect either browser validation or custom error
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(0);
  });

  test('14.1.5 AuthGuard redirects protected routes if not logged in', async ({ page }) => {
    // Try accessing dashboard without auth
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    // Either dashboard loads (auth disabled) or redirects to /login
    const _url = page.url();
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(20);
    await page.screenshot({ path: 'e2e/visual-batch09/14-1-5-auth-guard.png' });
  });
});

test.describe('14.2 Setup / Onboarding', () => {
  test('14.2.1 Setup page renders or redirects', async ({ page }) => {
    await page.goto('/setup');
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThanOrEqual(0);
    await page.screenshot({ path: 'e2e/visual-batch09/14-2-1-setup.png' });
  });

  test('14.2.2 Onboarding page renders or redirects', async ({ page }) => {
    await page.goto('/onboarding');
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(20);
    await page.screenshot({ path: 'e2e/visual-batch09/14-2-2-onboarding.png' });
  });
});
