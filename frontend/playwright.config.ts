import { defineConfig, devices } from "@playwright/test";

/**
 * Next.js dev server port for E2E tests.
 *
 * Port 3001 may be occupied by the Docker Grafana proxy in local development.
 * The V2 tests use port 3099 to avoid conflicts.
 */

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
    actionTimeout: 5_000,
  },
  webServer: {
    command: "npm run dev -- --port 3001",
    url: "http://localhost:3001",
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    // V2 layout tests — override baseURL to port 3099
    {
      name: "v2",
      testDir: "./tests/e2e/v2",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://localhost:3099",
      },
    },
    // Main E2E tests — default port 3001
    {
      name: "chromium",
      testDir: "./tests/e2e",
      testIgnore: ["v2/**"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
