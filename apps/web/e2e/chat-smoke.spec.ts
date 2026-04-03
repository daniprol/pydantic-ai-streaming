import { expect, test } from '@playwright/test'

test('basic flow shell renders', async ({ page }) => {
  await page.goto('/basic')

  await expect(page.getByText('Pydantic AI')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Basic' })).toBeVisible()
  await expect(page.getByPlaceholder('Ask about an order, service health, or support policy...')).toBeVisible()
})


test('basic flow keeps a conversation after reload', async ({ page }) => {
  const prompt = 'Persist this conversation through reload'

  await page.goto('/basic')
  await page.getByPlaceholder('Ask about an order, service health, or support policy...').fill(prompt)
  await page.keyboard.press('Enter')

  await expect(page).toHaveURL(/\/basic\/conversations\//)
  await expect(page.locator('a', { hasText: prompt }).first()).toBeVisible()
  await expect(page.locator('p', { hasText: prompt }).first()).toBeVisible()

  await page.reload()

  await expect(page).toHaveURL(/\/basic\/conversations\//)
  await expect(page.locator('a', { hasText: prompt }).first()).toBeVisible()
  await expect(page.locator('p', { hasText: prompt }).first()).toBeVisible()
})


test('made-up conversation URLs redirect to not found', async ({ page }) => {
  await page.goto('/basic/conversations/87319ab1-c3d1-4e7b-a238-5b932aef2e9a')

  await expect(page).toHaveURL(/\/not-found/)
  await expect(page.getByText('Conversation not found')).toBeVisible()
})
