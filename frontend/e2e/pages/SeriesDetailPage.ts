import type { Page } from '@playwright/test';
import { BasePage } from './BasePage';

export class SeriesDetailPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // Accepts a series id (number) while staying assignable to BasePage.goto(path: string).
  async goto(seriesId: number | string): Promise<void> {
    await super.goto(`/library/series/${seriesId}`);
  }

  get backBtn() {
    return this.page.locator('[data-testid="series-back-btn"]');
  }

  get title() {
    return this.page.locator('[data-testid="series-title"]');
  }

  get episodeRows() {
    return this.page.locator('[data-testid="episode-row"]');
  }

  get seasonGroups() {
    return this.page.locator('[data-testid="season-group"]');
  }

  get episodeActionMenus() {
    return this.page.locator('[data-testid="episode-actions-menu"]');
  }

  async waitForContent(): Promise<void> {
    await this.page.waitForSelector('[data-testid="series-title"]', { timeout: 20000 });
  }
}
