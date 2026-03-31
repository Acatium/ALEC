/**
 * E2E tests for system functionality
 * Tests run against real backend - NO MOCKS
 */

import { test, expect } from '@playwright/test';

const API_URL = process.env.VITE_API_URL || 'http://localhost:8008';

test.describe('System', () => {
  test('displays system dashboard', async ({ page }) => {
    await page.goto('/system');

    // Check for page elements
    await expect(page.getByRole('heading', { name: /system.*dashboard/i })).toBeVisible();
  });

  test('shows learning statistics', async ({ page }) => {
    await page.goto('/system');

    // Should display stats
    await expect(page.getByText(/total sessions/i)).toBeVisible();
    await expect(page.getByText(/total bullets/i)).toBeVisible();
  });

  test('displays health status', async ({ page }) => {
    await page.goto('/system');

    // Should show health indicator
    await expect(page.getByText(/healthy|degraded|unhealthy/i)).toBeVisible();
  });

  test('has reset controls', async ({ page }) => {
    await page.goto('/system');

    // Should have reset section
    await expect(page.getByText(/reset/i)).toBeVisible();
  });

  test('can navigate to services page', async ({ page }) => {
    await page.goto('/system');

    // Click services link
    await page.getByRole('link', { name: /services/i }).click();

    // Should be on services page
    await expect(page.url()).toContain('/services');
  });

  test('can navigate to prompts page', async ({ page }) => {
    await page.goto('/system');

    // Click prompts link
    await page.getByRole('link', { name: /prompts/i }).click();

    // Should be on prompts page
    await expect(page.url()).toContain('/prompts');
  });

  test('can navigate to learning loop page', async ({ page }) => {
    await page.goto('/system');

    // Click learning loop link
    await page.getByRole('link', { name: /learning.*loop/i }).click();

    // Should be on learning loop page
    await expect(page.url()).toContain('/learning-loop');
    await expect(page.getByText(/architecture/i)).toBeVisible();
  });

  test('learning loop page shows documentation', async ({ page }) => {
    await page.goto('/learning-loop');

    // Should display documentation content
    await expect(page.getByText(/reflector/i)).toBeVisible();
    await expect(page.getByText(/curator/i)).toBeVisible();
    await expect(page.getByText(/clusterer/i)).toBeVisible();
    await expect(page.getByText(/advisor/i)).toBeVisible();
  });

  test('reset confirmation dialog works', async ({ page }) => {
    await page.goto('/system');

    // Click a reset button
    const resetButtons = page.getByRole('button', { name: /reset/i });
    if ((await resetButtons.count()) > 0) {
      await resetButtons.first().click();

      // Should show confirmation dialog
      await expect(page.getByText(/confirm|are you sure/i)).toBeVisible();

      // Cancel the dialog
      const cancelButton = page.getByRole('button', { name: /cancel/i });
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
      }
    }
  });

  test('intelligence analysis section exists', async ({ page }) => {
    await page.goto('/system');

    // Should have intelligence section
    await expect(page.getByText(/intelligence/i)).toBeVisible();
  });

  test('services page loads', async ({ page }) => {
    await page.goto('/system/services');

    // Should display services page
    await expect(page.getByRole('heading', { name: /services/i })).toBeVisible();
  });

  test('prompts page loads', async ({ page }) => {
    await page.goto('/system/prompts');

    // Should display prompts page
    await expect(page.getByRole('heading', { name: /prompts/i })).toBeVisible();
  });
});
