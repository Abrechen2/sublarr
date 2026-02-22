import { Page } from '@playwright/test';
import { BasePage } from './BasePage';

export class WantedPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await super.goto('/wanted');
  }

  get list() {
    return this.page.locator('[data-testid="wanted-list"]');
  }

  get items() {
    return this.page.locator('[data-testid="wanted-item"]');
  }

  get filterStatus() {
    return this.page.locator('[data-testid="wanted-filter-status"]');
  }

  searchButtons() {
    return this.page.locator('[data-testid="wanted-search-btn"]');
  }

  processButtons() {
    return this.page.locator('[data-testid="wanted-process-btn"]');
  }

  async clickSearchOnItem(index: number): Promise<void> {
    await this.searchButtons().nth(index).click();
  }

  async clickProcessOnItem(index: number): Promise<void> {
    await this.processButtons().nth(index).click();
  }
}
