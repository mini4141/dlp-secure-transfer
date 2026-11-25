import { defineConfig } from "@playwright/test";

const reportDir = process.env.REPORT_DIR || "playwright-report";

export default defineConfig({
  testDir: "./tests",
  timeout: 180_000,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["junit", { outputFile: `${reportDir}/junit.xml` }],
    ["html", { outputFolder: `${reportDir}/html`, open: "never" }],
  ],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:18000",
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
