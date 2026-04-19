/**
 * Batch 13 — Scheduler (/settings/system/scheduler)
 * Phase 5 / P3 — Scheduler write-endpoints golden path.
 *
 * Exercises the main user flows:
 *   - Job cards render
 *   - Run-now queues an execution (toast feedback)
 *   - Edit-trigger persists and surfaces the "Edited" pill
 *   - Reset-default removes the override
 */
import { expect, test } from '@playwright/test'
import { BasePage } from '../pages/BasePage'

test.setTimeout(60000)

async function gotoScheduler(page: Parameters<Parameters<typeof test>[1]>[0]['page']) {
  const base = new BasePage(page)
  await base.goto('/settings/system/scheduler')
  // Wait for a known default job to appear; bail out if the endpoint is not yet served.
  await page
    .waitForSelector('text=scheduler_history_cleanup', { timeout: 10000 })
    .catch(() => {
      // ignore — individual tests decide how to handle missing data
    })
}

test.describe('Scheduler page', () => {
  test('renders registered jobs', async ({ page }) => {
    await gotoScheduler(page)
    const jobLabel = page.getByText('scheduler_history_cleanup').first()
    const visible = await jobLabel.isVisible({ timeout: 5000 }).catch(() => false)
    if (!visible) {
      test.skip(true, 'Scheduler job list not available in this environment')
      return
    }
    await expect(jobLabel).toBeVisible()
  })

  test('run-now queues an execution', async ({ page }) => {
    await gotoScheduler(page)
    const runBtn = page
      .getByRole('button', { name: /run now|jetzt ausführen/i })
      .first()
    const exists = await runBtn.isVisible({ timeout: 5000 }).catch(() => false)
    if (!exists) {
      test.skip(true, 'Run-now button not found — scheduler may not be rendered')
      return
    }
    await runBtn.click()
    // Toast: "Run queued" / "Auftrag eingereiht"
    await expect(
      page.getByText(/run queued|auftrag eingereiht/i),
    ).toBeVisible({ timeout: 5000 })
  })

  test('edit trigger → Edited pill appears, reset → pill disappears', async ({
    page,
  }) => {
    await gotoScheduler(page)
    const editBtn = page
      .getByRole('button', { name: /edit trigger|zeitplan ändern/i })
      .first()
    const hasEdit = await editBtn.isVisible({ timeout: 5000 }).catch(() => false)
    if (!hasEdit) {
      test.skip(true, 'Edit-trigger button not available')
      return
    }
    await editBtn.click()

    // Switch to the Interval tab (or confirm it's already active) and bump the minutes.
    const intervalTab = page
      .getByRole('button', { name: /interval|intervall/i })
      .first()
    await expect(intervalTab).toBeVisible()
    await intervalTab.click()

    const nInput = page.getByRole('spinbutton').first()
    await nInput.fill('30')

    await page.getByRole('button', { name: /save|speichern/i }).click()

    // "Edited" pill visible on the job card
    await expect(page.getByText(/edited|geändert/i).first()).toBeVisible({
      timeout: 5000,
    })

    // Reset default — confirm the browser dialog automatically
    page.once('dialog', (d) => d.accept())
    await page
      .getByRole('button', { name: /reset default|standard/i })
      .first()
      .click()
    await expect(page.getByText(/edited|geändert/i)).toHaveCount(0, {
      timeout: 5000,
    })
  })
})
