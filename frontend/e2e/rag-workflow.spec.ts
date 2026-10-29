import { expect, test } from '@playwright/test'

/*
 * The complete Retrieva workflow through the real UI and API:
 * register → log in → upload → process (extract, chunk, embed, index) → ask → retrieve →
 * rerank → generate → verify citations → open the supporting evidence at its source.
 */

const POLICY = `# Northwind Travel Policy

## Booking

All business travel must be booked through the company travel portal at least 14 days before departure.

## Flights

Economy class is standard for flights under six hours. Business class may be used for flights longer than six hours with director approval.

## Hotels

The nightly hotel limit is 180 EUR in most cities and 250 EUR in London, Paris and New York.
`

test('register, upload, ask, and trace the answer back to its source', async ({ page }) => {
  const stamp = Date.now()
  const email = `e2e-${stamp}@retrieva-e2e.example.com`
  const password = `E2e-Test-Pass-${stamp}!`

  // Register a new organization
  await page.goto('/register')
  await page.getByLabel('Full name').fill('E2E Tester')
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Organization name').fill(`E2E Org ${stamp}`)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Create organization' }).click()
  await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening), E2E/ })).toBeVisible()

  // Sign out and back in
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to Retrieva' })).toBeVisible()
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ })).toBeVisible()

  // Upload a document and wait until it is indexed
  await page.goto('/app/documents')
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await page.getByTestId('file-input').setInputFiles({
    name: 'travel-policy.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from(POLICY),
  })
  await page.getByRole('button', { name: /^Upload 1$/ }).click()
  await expect(page.getByText('Uploaded — processing', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByRole('row', { name: /travel policy/i }).getByText('Ready')).toBeVisible({ timeout: 120_000 })

  // Ask a question
  await page.goto('/app/chat')
  await page.getByLabel('Message').fill('What is the nightly hotel limit in London?')
  await page.getByLabel('Message').press('Enter')

  // The answer is grounded, cited, and verified
  const answer = page.locator('.prose-answer').last()
  await expect(answer).toContainText('250 EUR', { timeout: 150_000 })
  const citation = answer.getByRole('button', { name: /Show source S\d+/ }).first()
  await expect(citation).toBeVisible()
  await expect(page.getByText(/Verified against sources|Partly supported by sources/)).toBeVisible()

  // Open the evidence and follow it to the highlighted passage in the document
  await citation.click()
  const evidence = page.locator('#evidence-S1').first()
  await expect(evidence).toContainText(/travel policy/i)
  await expect(evidence.getByText(/Supports answer|Partial support/)).toBeVisible()
  await evidence.getByRole('link', { name: 'Open passage' }).click()
  await expect(page).toHaveURL(/\/app\/documents\/.+\?start=\d+&end=\d+/)
  await expect(page.locator('mark[data-highlight]').filter({ hasText: '250 EUR' })).toBeVisible()

  // An unrelated question is not answered from the document
  await page.goto('/app/chat')
  await page.getByLabel('Message').fill('What is the capital of Australia?')
  await page.getByLabel('Message').press('Enter')
  await expect(page.getByText('Evidence insufficient', { exact: true })).toBeVisible({ timeout: 150_000 })
})
