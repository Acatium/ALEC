/**
 * E2E tests for chat functionality
 * Tests run against real backend - NO MOCKS
 */

import { test, expect } from '@playwright/test';

const API_URL = process.env.VITE_API_URL || 'http://localhost:8008';

test.describe('Chat', () => {
  test.beforeEach(async ({ request }) => {
    // Reset sessions before each test
    await request.post(`${API_URL}/api/v1/system/reset/sessions?confirm=true`);
  });

  test('displays chat interface on home page', async ({ page }) => {
    await page.goto('/');

    // Check for chat interface elements
    await expect(page.getByPlaceholder(/type.*message/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /send/i })).toBeVisible();
  });

  test('can send a message and receive response', async ({ page }) => {
    await page.goto('/');

    // Type and send a message
    const input = page.getByPlaceholder(/type.*message/i);
    await input.fill('Hello, this is a test message');
    await page.getByRole('button', { name: /send/i }).click();

    // Wait for message to appear in the list
    await expect(page.getByText('Hello, this is a test message')).toBeVisible({ timeout: 10000 });

    // Wait for assistant response (may take a while with real backend)
    await expect(page.locator('[data-role="assistant"]')).toBeVisible({ timeout: 60000 });
  });

  test('creates a new session when sending first message', async ({ page, request }) => {
    await page.goto('/');

    // Get initial session count
    const initialResponse = await request.get(`${API_URL}/api/v1/chat/sessions`);
    const initialSessions = await initialResponse.json();
    const initialCount = initialSessions.sessions?.length ?? 0;

    // Send a message
    const input = page.getByPlaceholder(/type.*message/i);
    await input.fill('Create a new session test');
    await page.getByRole('button', { name: /send/i }).click();

    // Wait for response
    await expect(page.locator('[data-role="assistant"]')).toBeVisible({ timeout: 60000 });

    // Verify session was created
    const newResponse = await request.get(`${API_URL}/api/v1/chat/sessions`);
    const newSessions = await newResponse.json();
    expect(newSessions.sessions?.length).toBeGreaterThan(initialCount);
  });

  test('displays message history correctly', async ({ page }) => {
    await page.goto('/');

    // Send multiple messages
    const input = page.getByPlaceholder(/type.*message/i);

    await input.fill('First message');
    await page.getByRole('button', { name: /send/i }).click();
    await expect(page.locator('[data-role="assistant"]').first()).toBeVisible({ timeout: 60000 });

    await input.fill('Second message');
    await page.getByRole('button', { name: /send/i }).click();

    // Both messages should be visible
    await expect(page.getByText('First message')).toBeVisible();
    await expect(page.getByText('Second message')).toBeVisible();
  });
});
