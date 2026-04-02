import { expect, test } from '@playwright/test'

test('basic flow shell renders', async ({ page }) => {
  await page.goto('/basic')

  await expect(page.getByText('Multi-flow PydanticAI playground')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Basic' })).toBeVisible()
  await expect(page.getByPlaceholder('Ask about an order, service health, or support policy...')).toBeVisible()
})
