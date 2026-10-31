import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const token = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n").find(line => line.startsWith("OPERATOR_TOKEN="))!.slice("OPERATOR_TOKEN=".length);

test("light assistant home explains the workflow and opens the human queue", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: "/tmp/supportflow-light-login.png", fullPage: true });
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Your support assistant" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Helpful answers. A human touch when it matters." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your connected tools" })).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(247, 249, 253)");
  await page.screenshot({ path: "/tmp/supportflow-assistant-light.png", fullPage: true });
  await page.getByRole("button", { name: "Open human handoffs" }).click();
  await expect(page.getByRole("heading", { name: "Conversations for your team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No conversations waiting for handoff" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your support assistant" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/supportflow-assistant-mobile.png", fullPage: true });
});

test("human queue verifies uncertain notification and returns ownership to assistant", async ({ page }) => {
  const handoff = { message_id: "human-request", thread_id: "human-thread", subject: "Help with my account", sender: "customer@example.com", recipient: "agent@example.com", reasons: ["human_requested"], active: true, status: "uncertain", error: "InspectGmailBeforeRetry" };
  await page.route("**/api/backend/handoffs**", async route => {
    if (route.request().method() === "POST") {
      expect(route.request().url()).toContain("/reconcile");
      handoff.status = "sent"; handoff.error = "";
      return route.fulfill({ json: { status: "confirmed", email_resend: false } });
    }
    return route.fulfill({ json: [handoff] });
  });
  await page.route("**/api/backend/threads/human-thread/ownership", async route => {
    expect(route.request().postDataJSON()).toEqual({ paused: false, owner: "assistant" });
    handoff.active = false; handoff.status = "resolved";
    return route.fulfill({ json: { paused: false } });
  });
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await page.getByRole("button", { name: "Handoffs", exact: true }).click();
  await expect(page.getByText("Help with my account", { exact: true })).toBeVisible();
  await expect(page.getByText("agent@example.com", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry notification" })).toHaveCount(0);
  await page.getByRole("button", { name: "Verify Gmail notification" }).click();
  await expect(page.getByRole("status")).toContainText("No second alert was sent");
  await expect(page.getByText("Agent notified", { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "/tmp/supportflow-handoffs-light.png", fullPage: true });
  await page.getByRole("button", { name: "Resume assistant" }).click();
  await expect(page.getByText("Returned to assistant", { exact: true })).toBeVisible();
});
