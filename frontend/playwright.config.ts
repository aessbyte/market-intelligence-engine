import { defineConfig, devices } from '@playwright/test';

const externalBaseURL = process.env.TEST_BASE_URL;
const baseURL = externalBaseURL ?? 'http://127.0.0.1:8001';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.MIE_CHROMIUM
      ? { executablePath: process.env.MIE_CHROMIUM }
      : undefined,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    {
      name: 'android-360',
      use: {
        ...devices['Pixel 7'],
        viewport: { width: 360, height: 800 },
        deviceScaleFactor: 1,
      },
    },
  ],
  webServer: externalBaseURL
    ? undefined
    : [
        {
          command: `${process.env.MIE_TEST_PYTHON ?? '../.venv/bin/python'} ../scripts/test_web_server.py --port 8001 --frontend-dist dist`,
          url: 'http://127.0.0.1:8001/api/v1/health',
          timeout: 120_000,
          reuseExistingServer: false,
        },
      ],
});
