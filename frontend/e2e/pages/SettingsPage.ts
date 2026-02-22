import { Page } from '@playwright/test';
import { BasePage } from './BasePage';

export class SettingsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await super.goto('/settings');
  }

  tab(name: string) {
    return this.page.getByRole('tab', { name });
  }

  async clickTab(name: string): Promise<void> {
    await this.tab(name).click();
    await this.page.waitForTimeout(300);
  }
}
