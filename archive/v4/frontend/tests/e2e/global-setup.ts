/**
 * Global setup for Playwright tests
 * Verifies backend is running before tests start
 */

import { FullConfig } from '@playwright/test';

const BACKEND_URL = process.env.VITE_API_URL || 'http://localhost:8008';

async function globalSetup(config: FullConfig) {
  console.log('Verifying backend is running...');

  const maxRetries = 10;
  const retryDelay = 2000; // 2 seconds

  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/system/learning-stats`);
      if (response.ok) {
        console.log('Backend is ready!');
        return;
      }
    } catch (error) {
      console.log(`Backend not ready (attempt ${i + 1}/${maxRetries}), retrying...`);
    }
    await new Promise((resolve) => setTimeout(resolve, retryDelay));
  }

  throw new Error(
    `Backend at ${BACKEND_URL} is not available. ` +
      'Please ensure the backend is running with: docker-compose up -d'
  );
}

export default globalSetup;
