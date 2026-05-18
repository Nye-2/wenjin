import { defineConfig, devices } from "@playwright/test";

/**
 * Next.js dev server port for E2E tests.
 *
 * Port 3099 avoids collisions with local infra like Grafana while keeping all
 * workspace tests on the same dev server.
 */

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:3099",
    trace: "on-first-retry",
    actionTimeout: 5_000,
  },
  webServer: {
    command: "npm run dev -- --port 3099",
    url: "http://localhost:3099",
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    // Workspace layout tests
    {
      name: "v2",
      testDir: "./tests/e2e/v2",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://localhost:3099",
      },
    },
    // Main E2E tests
    {
      name: "chromium",
      testDir: "./tests/e2e",
      testIgnore: ["v2/**"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
