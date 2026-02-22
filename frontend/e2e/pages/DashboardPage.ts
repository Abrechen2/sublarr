import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await super.goto('/');
  }

  get statsCards() {
    return this.page.locator('[data-testid="stats-cards"]');
  }

  get statCard() {
    return this.page.locator('[data-testid="stat-card"]');
  }

  get recentActivity() {
    return this.page.locator('[data-testid="recent-activity"]');
  }
}
