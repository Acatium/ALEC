import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Determine API URLs based on environment
// In Docker: use service names, otherwise use localhost
// Note: bullet-curator and agent-curator were merged into session service
const sessionUrl = process.env.VITE_API_URL || 'http://localhost:8008';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0', // Required for Docker
    port: 3001,
    proxy: {
      '/api': {
        target: sessionUrl,
        changeOrigin: true,
      },
      '/ws': {
        target: sessionUrl.replace('http', 'ws'),
        ws: true,
      },
      // Proxy for bullet-curator API (now served by session service)
      '/curator-api': {
        target: sessionUrl,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/curator-api/, '/api'),
      },
      // Proxy for agent-curator API (now served by session service)
      '/agent-api': {
        target: sessionUrl,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/agent-api/, '/api'),
      },
    },
  },
});
