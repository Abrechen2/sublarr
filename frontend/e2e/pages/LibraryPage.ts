import { Page } from '@playwright/test';
import { BasePage } from './BasePage';

export class LibraryPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await super.goto('/library');
  }

  get searchInput() {
    return this.page.locator('[data-testid="library-search"]');
  }

  get rows() {
    return this.page.locator('[data-testid="library-row"]');
  }

  get tabSeries() {
    return this.page.locator('[data-testid="tab-series"]');
  }

  get tabMovies() {
    return this.page.locator('[data-testid="tab-movies"]');
  }

  get paginationPrev() {
    return this.page.locator('[data-testid="pagination-prev"]');
  }

  get paginationNext() {
    return this.page.locator('[data-testid="pagination-next"]');
  }

  async search(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(400);
  }

  async clickRow(index: number): Promise<void> {
    await this.rows.nth(index).click();
    await this.waitForReady();
  }
}
