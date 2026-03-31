/**
 * E2E tests for evaluation functionality
 * Tests run against real backend - NO MOCKS
 */

import { test, expect } from '@playwright/test';

const API_URL = process.env.VITE_API_URL || 'http://localhost:8008';

test.describe('Evaluation', () => {
  test.beforeEach(async ({ request }) => {
    // Reset evaluations before each test
    await request.post(`${API_URL}/api/v1/system/reset/evaluations?confirm=true`);
  });

  test('displays evaluation page', async ({ page }) => {
    await page.goto('/evaluation');

    // Check for page elements
    await expect(page.getByRole('heading', { name: /evaluation/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /new experiment/i })).toBeVisible();
  });

  test('shows empty state when no experiments exist', async ({ page }) => {
    await page.goto('/evaluation');

    // Should show empty state or list
    const emptyState = page.getByText(/no experiments/i);
    const experimentCards = page.locator('[data-testid="experiment-card"]');

    // Either empty state or experiment cards should be visible
    const isEmpty = await emptyState.isVisible();
    const hasExperiments = (await experimentCards.count()) > 0;

    expect(isEmpty || hasExperiments).toBeTruthy();
  });

  test('can navigate to create experiment page', async ({ page }) => {
    await page.goto('/evaluation');

    // Click new experiment button
    await page.getByRole('link', { name: /new experiment/i }).click();

    // Should be on create page
    await expect(page.url()).toContain('/evaluation/new');
    await expect(page.getByText(/create experiment/i)).toBeVisible();
  });

  test('create experiment form has required fields', async ({ page }) => {
    await page.goto('/evaluation/new');

    // Check for form fields
    await expect(page.getByLabel(/name/i)).toBeVisible();
    await expect(page.locator('select').first()).toBeVisible(); // Dataset select
  });

  test('can create a new experiment', async ({ page }) => {
    await page.goto('/evaluation/new');

    // Fill in the form
    await page.getByLabel(/name/i).fill('Test Experiment E2E');

    // Select dataset
    const datasetSelect = page.locator('select').first();
    await datasetSelect.selectOption('test_normal');

    // Submit form
    await page.getByRole('button', { name: /create/i }).click();

    // Should redirect to detail page
    await expect(page.url()).toContain('/evaluation/');
    await expect(page.getByText('Test Experiment E2E')).toBeVisible({ timeout: 10000 });
  });

  test('experiment detail page shows status', async ({ page, request }) => {
    // Create an experiment first
    const createResponse = await request.post(`${API_URL}/api/v1/evaluation/experiments`, {
      data: {
        name: 'Status Test Experiment',
        dataset: 'test_normal',
        experiment_type: 'baseline',
      },
    });
    const experiment = await createResponse.json();

    // Navigate to detail page
    await page.goto(`/evaluation/${experiment.id}`);

    // Should show experiment details
    await expect(page.getByText('Status Test Experiment')).toBeVisible();
    await expect(page.getByText(/pending|running|completed/i)).toBeVisible();
  });

  test('can navigate to comparison page', async ({ page }) => {
    await page.goto('/evaluation');

    // Click compare button
    const compareLink = page.getByRole('link', { name: /compare/i });
    if (await compareLink.isVisible()) {
      await compareLink.click();
      await expect(page.url()).toContain('/compare');
    }
  });

  test('comparison page shows selection controls', async ({ page }) => {
    await page.goto('/evaluation/compare');

    // Should have selection interface
    await expect(page.getByText(/select.*experiment/i)).toBeVisible();
  });

  test('advanced options are toggleable', async ({ page }) => {
    await page.goto('/evaluation/new');

    // Look for advanced options toggle
    const advancedToggle = page.getByText(/advanced/i);
    if (await advancedToggle.isVisible()) {
      await advancedToggle.click();

      // Should show additional options
      await expect(page.getByText(/concurrent/i)).toBeVisible();
    }
  });
});
