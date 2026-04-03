import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'uv run --project ../api python -m streaming_chat_api.e2e_server',
      port: 8001,
      reuseExistingServer: true,
      timeout: 120000,
    },
    {
      command: 'pnpm dev --host 127.0.0.1 --port 5173',
      env: {
        ...process.env,
        VITE_API_BASE_URL: 'http://127.0.0.1:8001',
      },
      port: 5173,
      reuseExistingServer: true,
      timeout: 120000,
    },
  ],
})
