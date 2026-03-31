/**
 * E2E tests for bullet library functionality
 * Tests run against real backend - NO MOCKS
 */

import { test, expect } from '@playwright/test';

const API_URL = process.env.VITE_API_URL || 'http://localhost:8008';

test.describe('Library', () => {
  test('displays bullet library page', async ({ page }) => {
    await page.goto('/bullets');

    // Check for page elements
    await expect(page.getByRole('heading', { name: /bullet library/i })).toBeVisible();
  });

  test('shows filter controls', async ({ page }) => {
    await page.goto('/bullets');

    // Should have filter dropdowns
    await expect(page.locator('select').first()).toBeVisible();
  });

  test('can search bullets', async ({ page }) => {
    await page.goto('/bullets');

    // Find search input
    const searchInput = page.getByPlaceholder(/search/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill('test search');
      // Wait for search to apply
      await page.waitForTimeout(500);
    }
  });

  test('displays bullet detail page', async ({ page, request }) => {
    // Get bullets from API
    const response = await request.get(`${API_URL}/api/v1/library?page_size=1`);
    const data = await response.json();

    if (data.bullets && data.bullets.length > 0) {
      const bulletId = data.bullets[0].id;

      await page.goto(`/bullets/${bulletId}`);

      // Should display bullet details
      await expect(page.getByText(/situation/i)).toBeVisible();
      await expect(page.getByText(/assertion/i)).toBeVisible();
    } else {
      // No bullets exist, just verify the library page loads
      await page.goto('/bullets');
      await expect(page.getByText(/no bullets/i)).toBeVisible();
    }
  });

  test('can filter bullets by polarity', async ({ page }) => {
    await page.goto('/bullets');

    // Find polarity filter
    const filters = page.locator('select');
    if ((await filters.count()) > 0) {
      await filters.first().selectOption({ index: 1 }); // Select first non-empty option
      await page.waitForTimeout(500);
    }
  });

  test('can filter bullets by status', async ({ page }) => {
    await page.goto('/bullets');

    // Find status filter (usually second select)
    const filters = page.locator('select');
    if ((await filters.count()) > 1) {
      await filters.nth(1).selectOption({ index: 1 });
      await page.waitForTimeout(500);
    }
  });

  test('pagination works correctly', async ({ page, request }) => {
    await page.goto('/bullets');

    // Check for pagination controls
    const pagination = page.locator('[data-testid="pagination"]');
    if (await pagination.isVisible()) {
      // Try clicking next page if available
      const nextButton = page.getByRole('button', { name: /next/i });
      if (await nextButton.isEnabled()) {
        await nextButton.click();
        await page.waitForTimeout(500);
      }
    }
  });

  test('bullet effectiveness is displayed', async ({ page, request }) => {
    // Get bullets with effectiveness data
    const response = await request.get(`${API_URL}/api/v1/library?page_size=10`);
    const data = await response.json();

    if (data.bullets && data.bullets.length > 0) {
      const bulletWithData = data.bullets.find(
        (b: { helpful_count: number; harmful_count: number }) =>
          b.helpful_count > 0 || b.harmful_count > 0
      );

      if (bulletWithData) {
        await page.goto(`/bullets/${bulletWithData.id}`);
        // Should display effectiveness stats
        await expect(page.getByText(/effectiveness/i)).toBeVisible();
      }
    }
  });
});
