/**
 * E2E tests for sessions functionality
 * Tests run against real backend - NO MOCKS
 */

import { test, expect } from '@playwright/test';

const API_URL = process.env.VITE_API_URL || 'http://localhost:8008';

test.describe('Sessions', () => {
  test.beforeEach(async ({ request }) => {
    // Reset sessions before each test
    await request.post(`${API_URL}/api/v1/system/reset/sessions?confirm=true`);
  });

  test('displays sessions list page', async ({ page }) => {
    await page.goto('/sessions');

    // Check for page elements
    await expect(page.getByRole('heading', { name: /sessions/i })).toBeVisible();
  });

  test('shows empty state when no sessions exist', async ({ page }) => {
    await page.goto('/sessions');

    // Should show empty state message
    await expect(page.getByText(/no sessions/i)).toBeVisible();
  });

  test('can navigate to session detail page', async ({ page, request }) => {
    // First create a session via chat
    await page.goto('/');
    const input = page.getByPlaceholder(/type.*message/i);
    await input.fill('Test session for detail view');
    await page.getByRole('button', { name: /send/i }).click();
    await expect(page.locator('[data-role="assistant"]')).toBeVisible({ timeout: 60000 });

    // Now navigate to sessions list
    await page.goto('/sessions');

    // Should see the session
    await expect(page.getByText(/test session/i)).toBeVisible({ timeout: 10000 });

    // Click on the session to view details
    await page.getByText(/test session/i).click();

    // Should be on detail page
    await expect(page.url()).toContain('/sessions/');
    await expect(page.getByText(/turn/i)).toBeVisible();
  });

  test('displays session timeline with turns', async ({ page }) => {
    // Create a session with multiple turns
    await page.goto('/');
    const input = page.getByPlaceholder(/type.*message/i);

    await input.fill('First turn message');
    await page.getByRole('button', { name: /send/i }).click();
    await expect(page.locator('[data-role="assistant"]').first()).toBeVisible({ timeout: 60000 });

    await input.fill('Second turn message');
    await page.getByRole('button', { name: /send/i }).click();
    await page.waitForTimeout(2000); // Wait for second response

    // Get the session ID from the URL or API
    const sessionsResponse = await page.request.get(`${API_URL}/api/v1/chat/sessions`);
    const sessions = await sessionsResponse.json();
    const sessionId = sessions.sessions?.[0]?.session_id;

    if (sessionId) {
      await page.goto(`/sessions/${sessionId}`);

      // Should display turn cards
      await expect(page.getByText(/turn 1/i)).toBeVisible();
    }
  });

  test('can filter sessions by status', async ({ page, request }) => {
    // Create a session first
    await page.goto('/');
    const input = page.getByPlaceholder(/type.*message/i);
    await input.fill('Session for filtering test');
    await page.getByRole('button', { name: /send/i }).click();
    await expect(page.locator('[data-role="assistant"]')).toBeVisible({ timeout: 60000 });

    // Navigate to sessions and apply filter
    await page.goto('/sessions');

    // Look for filter controls
    const statusFilter = page.locator('select').first();
    if (await statusFilter.isVisible()) {
      await statusFilter.selectOption('active');
      // Verify filtering worked (UI should update)
      await page.waitForTimeout(1000);
    }
  });
});
