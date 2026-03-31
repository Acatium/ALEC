/**
 * Playwright configuration
 * Tests run against real backend - NO MOCKS
 */

import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.VITE_APP_URL || 'http://localhost:3001';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false, // Sequential execution to avoid race conditions
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker for consistent state
  reporter: [['html', { open: 'never' }], ['list']],
  globalSetup: './tests/e2e/global-setup.ts',

  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Start dev server before tests
  webServer: {
    command: 'npm run dev',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
