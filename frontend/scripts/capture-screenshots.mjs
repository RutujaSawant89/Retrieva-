/**
 * Capture real screenshots of the running application (used for the case-study gallery).
 *
 *   RETRIEVA_EMAIL=... RETRIEVA_PASSWORD=... node scripts/capture-screenshots.mjs [outDir] [--mobile]
 *
 * Requires the API on :8000 and the web app on BASE_URL (default http://localhost:5173), with
 * documents, conversations and evaluation runs already present in the account.
 */
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

import { chromium } from '@playwright/test'

const BASE = process.env.BASE_URL ?? 'http://localhost:5173'
const outDir = path.resolve(process.argv[2] ?? 'public/case-study')
const mobile = process.argv.includes('--mobile')
const theme = process.env.THEME ?? 'light'

const PAGES = [
  { name: 'dashboard', path: '/app' },
  { name: 'documents', path: '/app/documents' },
  { name: 'chat', path: '/app/chat', setup: openLatestConversation },
  { name: 'search', path: '/app/search', setup: runSearch },
  { name: 'research', path: '/app/research', setup: openLatestReport },
  { name: 'compare', path: '/app/compare', setup: runCompare },
  { name: 'evaluation', path: '/app/evaluation' },
  { name: 'analytics', path: '/app/analytics' },
  { name: 'collections', path: '/app/collections' },
  { name: 'admin', path: '/app/admin' },
  { name: 'settings', path: '/app/settings' },
]

async function openLatestConversation(page) {
  // Below 2xl the conversation list lives behind the "History" button.
  const history = page.getByRole('button', { name: /conversation history/i })
  if (await history.isVisible().catch(() => false)) await history.click()
  const first = page.locator('nav[aria-label="Conversations"] a:visible').first()
  if (await first.count()) {
    await first.click()
    await page.waitForTimeout(1500)
    const cite = page.getByRole('button', { name: /Show source S1/ }).last()
    if (await cite.count()) await cite.click()
  }
}

async function runSearch(page) {
  const box = page.getByLabel('Search query')
  await box.fill('How much notice is needed to terminate the agreement?')
  await box.press('Enter')
  await page.getByText(/passages, chosen from/).waitFor({ timeout: 120_000 }).catch(() => {})
  await page.waitForTimeout(500)
}

async function openLatestReport(page) {
  // RUN_RESEARCH=1 creates a real report first when the workspace has none.
  if (process.env.RUN_RESEARCH && !(await page.locator('[data-report-link]').count())) {
    await page.locator('textarea').first().fill(
      'How do the Northwind agreements and policies handle termination notice, data protection and annual leave?',
    )
    await page.getByRole('button', { name: /Run research/ }).click()
    await page.locator('[data-report-link]').first().waitFor({ timeout: 300_000 }).catch(() => {})
  }
  const first = page.locator('[data-report-link]').first()
  if (await first.count()) {
    await first.click()
    await page.waitForTimeout(2000)
  }
}

async function runCompare(page) {
  const selects = page.locator('[aria-label="First document"], [aria-label="Second document"]')
  if ((await selects.count()) < 2) return
  for (const [index, option] of [
    [0, 1],
    [1, 2],
  ]) {
    await selects.nth(index).click()
    const options = page.getByRole('option')
    if ((await options.count()) > option) await options.nth(option).click()
    else await page.keyboard.press('Escape')
  }
  await page.getByRole('button', { name: /^Compare$/ }).click()
  await page.waitForTimeout(4000)
}

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
  deviceScaleFactor: mobile ? 2 : 1,
  colorScheme: theme,
})
const page = await context.newPage()
await page.goto(`${BASE}/login`)
await page.getByLabel('Work email').fill(process.env.RETRIEVA_EMAIL)
await page.getByLabel('Password').fill(process.env.RETRIEVA_PASSWORD)
await page.getByRole('button', { name: 'Sign in' }).click()
await page.waitForURL('**/app')
await mkdir(outDir, { recursive: true })

const only = process.env.ONLY?.split(',')
for (const target of PAGES) {
  if (only && !only.includes(target.name)) continue
  await page.goto(`${BASE}${target.path}`)
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(1200)
  if (target.setup) await target.setup(page).catch((error) => console.warn(target.name, error.message))
  const file = path.join(outDir, `${target.name}${mobile ? '-mobile' : ''}${theme === 'dark' ? '-dark' : ''}.png`)
  await page.screenshot({ path: file })
  console.log('saved', file)
}
await browser.close()
