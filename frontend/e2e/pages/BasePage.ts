import { Page, expect } from '@playwright/test';

export class BasePage {
  constructor(protected readonly page: Page) {}

  async goto(path: string): Promise<void> {
    await this.page.goto(path);
    // domcontentloaded avoids hanging on Vite HMR WebSocket which prevents networkidle
    await this.page.waitForLoadState('domcontentloaded', { timeout: 15000 });
  }

  async waitForReady(): Promise<void> {
    await this.page.waitForLoadState('domcontentloaded', { timeout: 15000 });
  }

  get sidebar() {
    return this.page.locator('[data-testid="sidebar"]');
  }

  get navLinks() {
    return this.page.locator('[data-testid="sidebar-nav"] a');
  }

  async navigateTo(linkTestId: string): Promise<void> {
    await this.page.locator(`[data-testid="${linkTestId}"]`).click();
    await this.waitForReady();
  }

  async expectCurrentPath(path: string): Promise<void> {
    await expect(this.page).toHaveURL(new RegExp(path));
  }

  get healthIndicator() {
    return this.page.locator('[data-testid="health-indicator"]');
  }

  get toast() {
    return this.page.locator('[data-testid="toast"]').first();
  }

  async waitForToast(text?: string): Promise<void> {
    await expect(this.toast).toBeVisible({ timeout: 10000 });
    if (text) await expect(this.toast).toContainText(text);
  }
}
