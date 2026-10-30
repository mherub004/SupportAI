import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const env = Object.fromEntries(fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8")
  .split("\n").filter(line => line && !line.startsWith("#") && line.includes("="))
  .map(line => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));

test("operator reviews grounded draft, inspects risk, and pauses thread", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(env.OPERATOR_TOKEN);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Your review workspace" })).toBeVisible();
  await expect(page.getByText("Synthetic customers and documents. No real email is sent.")).toBeVisible();
  await page.screenshot({ path: "/tmp/supportflow-inbox.png", fullPage: true });
  await page.getByRole("button", { name: /Manual for ABL DEMO-1/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const close = dialog.getByRole("button", { name: "Close review" });
  await close.focus();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByLabel("Review / correction reason")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await expect(dialog.getByRole("heading", { name: "Supporting evidence" })).toBeVisible();
  await expect(dialog.locator("blockquote")).toContainText("Synthetic demo document");
  await expect(dialog.getByLabel("Response draft")).toContainText("https://example.invalid/");
  await expect(dialog.getByRole("button", { name: "Send approved reply" })).toBeDisabled();
  await dialog.getByLabel("Review / correction reason").fill("Verified synthetic source and recipient for UI test");
  await dialog.getByRole("button", { name: "Approve response" }).click();
  await expect(page.getByRole("status")).toContainText("approved");
  await dialog.getByRole("button", { name: "Take over" }).click();
  await expect(dialog.getByText("Human owns this thread")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Send approved reply" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Resume agent" }).click();
  await expect(dialog.getByText("Agent may prepare drafts")).toBeVisible();
  await dialog.getByRole("button", { name: "Close review" }).click();
  await page.getByRole("button", { name: /Wallbox smoking/ }).click();
  await expect(dialog.getByText("Human attention required")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Approve response" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Close review" }).click();
  await page.getByRole("button", { name: "Knowledge", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Source registry" })).toBeVisible();
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
  await expect(page.getByText("response approved", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Operations", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Mailbox kill switch" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Enable sending" })).toBeVisible();
  await page.screenshot({ path: "/tmp/supportflow-operations.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("mobile workspace fits viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(env.OPERATOR_TOKEN);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Your review workspace" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/supportflow-mobile.png", fullPage: true });
});
