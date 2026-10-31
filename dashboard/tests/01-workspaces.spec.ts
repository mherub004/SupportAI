import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const token = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n").find(line => line.startsWith("OPERATOR_TOKEN="))!.slice("OPERATOR_TOKEN=".length);

test("company and personal test keep knowledge separate across switches and browser tabs", async ({ page, context }) => {
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Set up your business" })).toBeVisible();
  const origin = new URL(page.url()).origin;
  for (const workspace of ["company", "test"]) {
    const result = await page.request.put(`${origin}/api/backend/knowledge`, {
      headers: { Origin: origin, "X-SupportFlow-Workspace": workspace },
      data: { id: "workspace-check", title: `${workspace} private knowledge`, revision: "1", brand: "Workspace check", model: "general", language: "en", owner: "Synthetic tester", content: `Synthetic ${workspace} knowledge, isolated from the other environment.`, approved: true, effective_at: "2026-01-01T00:00:00Z", url: "https://example.invalid/workspace" },
    });
    expect(result.ok()).toBe(true);
  }
  await page.getByRole("button", { name: "Personal test environment", exact: true }).click();
  await expect(page).toHaveURL(/workspace=test/);
  await expect(page.getByRole("heading", { name: "Try your personal inbox" })).toBeVisible();
  await page.getByRole("button", { name: "Knowledge", exact: true }).click();
  await expect(page.getByRole("heading", { name: "test private knowledge" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "company private knowledge" })).toHaveCount(0);
  const company = await context.newPage();
  await company.goto("/");
  await expect(company.getByRole("heading", { name: "Set up your business" })).toBeVisible();
  await company.getByRole("button", { name: "Knowledge", exact: true }).click();
  await expect(company.getByRole("heading", { name: "company private knowledge" })).toBeVisible();
  await expect(company.getByRole("heading", { name: "test private knowledge" })).toHaveCount(0);
  await company.getByRole("button", { name: "Company workspace", exact: true }).click();
  await page.getByRole("button", { name: "Refresh", exact: false }).click();
  await expect(page.getByRole("heading", { name: "test private knowledge" })).toBeVisible();
});

test("workspace selection requires authentication, same origin and a supported environment", async ({ request, page }) => {
  const origin = process.env.DASHBOARD_URL || "http://localhost:3000";
  expect((await request.post(`${origin}/api/workspace`, { headers: { Origin: origin }, data: { workspace: "test" } })).status()).toBe(401);
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  expect((await page.request.post(`${origin}/api/workspace`, { headers: { Origin: "https://attacker.invalid" }, data: { workspace: "test" } })).status()).toBe(403);
  expect((await page.request.post(`${origin}/api/workspace`, { headers: { Origin: origin }, data: { workspace: "unknown" } })).status()).toBe(400);
});
