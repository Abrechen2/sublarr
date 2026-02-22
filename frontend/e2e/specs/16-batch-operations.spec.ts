/**
 * E2E tests for batch operation features introduced in v0.11.1-beta:
 * - Library series checkboxes + batch toolbar
 * - SeriesDetail episode checkboxes + batch toolbar
 * - Settings: wanted_auto_extract / wanted_auto_translate toggles
 */

import { test, expect } from '@playwright/test'
import { LibraryPage } from '../pages/LibraryPage'
import { SettingsPage } from '../pages/SettingsPage'
import { ANIME } from '../fixtures/anime'

// ---------------------------------------------------------------------------
// Library batch toolbar
// ---------------------------------------------------------------------------

test.describe('Library batch operations', () => {
  let library: LibraryPage

  test.beforeEach(async ({ page }) => {
    library = new LibraryPage(page)
    await library.goto()
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 })
  })

  test('each library row has a checkbox', async ({ page }) => {
    const firstCheckbox = library.rows.first().locator('input[type="checkbox"]')
    await expect(firstCheckbox).toBeVisible()
  })

  test('batch toolbar is hidden when nothing is selected', async ({ page }) => {
    const toolbar = page.locator('text=series selected')
    await expect(toolbar).not.toBeVisible()
  })

  test('checking a row shows the batch toolbar', async ({ page }) => {
    const firstCheckbox = library.rows.first().locator('input[type="checkbox"]')
    await firstCheckbox.click()

    const toolbar = page.locator('text=series selected')
    await expect(toolbar).toBeVisible({ timeout: 3000 })

    const searchBtn = page.locator('button:has-text("Search All Missing")')
    await expect(searchBtn).toBeVisible()
  })

  test('checking two rows shows correct count in toolbar', async ({ page }) => {
    const checkboxes = library.rows.locator('input[type="checkbox"]')
    await checkboxes.nth(0).click()
    await checkboxes.nth(1).click()

    await expect(page.locator('text=2 series selected')).toBeVisible({ timeout: 3000 })
  })

  test('Clear button deselects all and hides toolbar', async ({ page }) => {
    const firstCheckbox = library.rows.first().locator('input[type="checkbox"]')
    await firstCheckbox.click()
    await expect(page.locator('text=series selected')).toBeVisible({ timeout: 3000 })

    await page.locator('button:has-text("Clear")').first().click()

    await expect(page.locator('text=series selected')).not.toBeVisible({ timeout: 3000 })
    await expect(firstCheckbox).not.toBeChecked()
  })

  test('table header has select-all checkbox', async ({ page }) => {
    const headerCheckbox = page.locator('thead input[type="checkbox"]')
    await expect(headerCheckbox).toBeVisible()
  })

  test('select-all checkbox selects all visible rows', async ({ page }) => {
    const rowCount = await library.rows.count()
    if (rowCount < 2) test.skip()

    const headerCheckbox = page.locator('thead input[type="checkbox"]')
    await headerCheckbox.click()

    // Toolbar should show the count
    const toolbar = page.locator('text=series selected')
    await expect(toolbar).toBeVisible({ timeout: 3000 })

    // All row checkboxes should be checked
    const rowCheckboxes = library.rows.locator('input[type="checkbox"]')
    const allChecked = await rowCheckboxes.evaluateAll(
      (boxes: HTMLInputElement[]) => boxes.every(b => b.checked)
    )
    expect(allChecked).toBe(true)
  })

  test('Search All Missing button triggers batch search and hides toolbar', async ({ page }) => {
    const firstCheckbox = library.rows.first().locator('input[type="checkbox"]')
    await firstCheckbox.click()
    await expect(page.locator('text=series selected')).toBeVisible({ timeout: 3000 })

    const searchBtn = page.locator('button:has-text("Search All Missing")')
    await searchBtn.click()

    // Toolbar should disappear (selection cleared after action)
    await expect(page.locator('text=series selected')).not.toBeVisible({ timeout: 5000 })
  })
})

// ---------------------------------------------------------------------------
// SeriesDetail episode batch toolbar
// ---------------------------------------------------------------------------

test.describe('SeriesDetail episode batch operations', () => {
  let library: LibraryPage

  test.beforeEach(async ({ page }) => {
    library = new LibraryPage(page)
    await library.goto()
    await expect(library.rows.first()).toBeVisible({ timeout: 10000 })
    // Navigate to My Dress-Up Darling detail page
    await library.search(ANIME.dressDarling.titlePart)
    await expect(library.rows.first()).toBeVisible({ timeout: 5000 })
    await library.clickRow(0)
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 })
    await page.waitForTimeout(1000)
  })

  test('episode rows have checkboxes', async ({ page }) => {
    // Wait for episodes to load
    const checkbox = page.locator('input[type="checkbox"]').nth(1) // skip any header checkbox
    await expect(checkbox).toBeVisible({ timeout: 10000 })
  })

  test('batch toolbar is hidden initially', async ({ page }) => {
    await expect(page.locator('text=selected')).not.toBeVisible()
  })

  test('checking an episode shows batch toolbar', async ({ page }) => {
    // Find episode checkboxes (not header)
    const episodeCheckboxes = page.locator('input[type="checkbox"]')
    const count = await episodeCheckboxes.count()
    if (count < 2) test.skip()

    // Click second checkbox (first might be the season select-all)
    await episodeCheckboxes.nth(1).click()

    await expect(page.locator('text=selected')).toBeVisible({ timeout: 3000 })

    const batchToolbar = page.locator('[data-testid="episode-batch-toolbar"]')
    await expect(batchToolbar.locator('button:has-text("Search")')).toBeVisible()
    await expect(batchToolbar.locator('button:has-text("Extract")')).toBeVisible()
  })

  test('Clear button in episode toolbar deselects', async ({ page }) => {
    const episodeCheckboxes = page.locator('input[type="checkbox"]')
    const count = await episodeCheckboxes.count()
    if (count < 2) test.skip()

    await episodeCheckboxes.nth(1).click()
    await expect(page.locator('text=selected')).toBeVisible({ timeout: 3000 })

    const clearBtn = page.locator('button:has-text("Clear")').first()
    await clearBtn.click()

    await expect(page.locator('text=selected')).not.toBeVisible({ timeout: 3000 })
  })

  test('multiple episodes can be selected', async ({ page }) => {
    const episodeCheckboxes = page.locator('input[type="checkbox"]')
    const count = await episodeCheckboxes.count()
    if (count < 3) test.skip()

    await episodeCheckboxes.nth(1).click()
    await episodeCheckboxes.nth(2).click()

    await expect(page.locator('text=2 selected')).toBeVisible({ timeout: 3000 })
  })
})

// ---------------------------------------------------------------------------
// Settings: auto-extract toggles
// ---------------------------------------------------------------------------

test.describe('Settings auto-extract toggles', () => {
  let settings: SettingsPage

  test.beforeEach(async ({ page }) => {
    settings = new SettingsPage(page)
    await settings.goto()
  })

  test('wanted_auto_extract toggle is visible in Wanted tab', async ({ page }) => {
    // Navigate to Wanted settings tab
    const wantedTab = page.locator('button:has-text("Wanted"), [role="tab"]:has-text("Wanted")').first()
    const tabVisible = await wantedTab.isVisible().catch(() => false)

    if (tabVisible) {
      await wantedTab.click()
      await page.waitForTimeout(500)
    }

    // Look for the auto-extract label
    const label = page.locator('text=Auto-extract embedded subs on scan')
    await expect(label).toBeVisible({ timeout: 5000 })
  })

  test('wanted_auto_translate toggle is visible', async ({ page }) => {
    const wantedTab = page.locator('button:has-text("Wanted"), [role="tab"]:has-text("Wanted")').first()
    const tabVisible = await wantedTab.isVisible().catch(() => false)

    if (tabVisible) {
      await wantedTab.click()
      await page.waitForTimeout(500)
    }

    const label = page.locator('text=Auto-translate after extraction')
    await expect(label).toBeVisible({ timeout: 5000 })
  })
})
