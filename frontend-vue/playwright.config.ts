import { defineConfig } from '@playwright/test';

// 阶段6 Vue 页面 smoke. 沿用本机 Chrome (channel chrome) 避免下载 chromium;
// CI 下用默认 chromium. webServer 起 vite dev (5174), API 全部由 page.route mock.
const localBrowserChannel = process.env.E2E_BROWSER_CHANNEL || (process.env.CI ? undefined : 'chrome');

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    channel: localBrowserChannel,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
