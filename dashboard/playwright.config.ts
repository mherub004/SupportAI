import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 30000, workers: 1,
  use: { baseURL: "http://localhost:3000", headless: true,
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {} },
});
