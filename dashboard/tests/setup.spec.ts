import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const env = Object.fromEntries(fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8")
  .split("\n").filter(line => line && !line.startsWith("#") && line.includes("="))
  .map(line => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));

test("company configures profile, approved knowledge and encrypted connection after deployment", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(env.OPERATOR_TOKEN);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await page.getByRole("button", { name: "Business setup", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your business" })).toBeVisible();
  const setup = page.locator(".setup-workspace");
  await setup.getByLabel("Company name", { exact: true }).fill("Acme Services UI");
  await setup.getByLabel("Industry / business type").fill("Customer services");
  await setup.getByLabel("Support mailbox", { exact: true }).fill("support@acme.example");
  await setup.getByLabel("Human escalation contact").fill("human@acme.example");
  await setup.getByLabel(/I am authorized/).check();
  await setup.getByRole("button", { name: "Save company profile" }).click();
  await expect(setup.getByRole("status")).toContainText("Company profile saved");
  await expect(page.getByText("Setup in progress", { exact: true })).toBeVisible();
  await setup.getByText("Or paste an approved source manually", { exact: true }).click();
  await setup.getByLabel("Source title", { exact: true }).fill("Acme customer account FAQ");
  await setup.getByLabel("Business / product family").fill("Acme Services UI");
  await setup.getByLabel("Knowledge owner").fill("Demo reviewer");
  await setup.getByLabel("Internal source URL").fill("https://example.invalid/acme/faq");
  await setup.getByLabel("Approved source text").fill("Synthetic Acme account FAQ for browser testing. This is not a real company document.");
  await setup.getByLabel("This source is current").check();
  await setup.getByRole("button", { name: "Save knowledge source" }).click();
  await expect(setup.getByRole("status")).toContainText("Knowledge source saved");
  const gemini = setup.locator(".connector-card").filter({ has: page.getByRole("heading", { name: "Gemini", exact: true }) });
  await gemini.getByLabel("Gemini API key").fill("synthetic-browser-key-not-a-real-credential");
  await gemini.getByLabel("Approved model ID").fill("gemini-2.5-flash");
  await gemini.getByRole("button", { name: "Save connection", exact: true }).click();
  await expect(setup.getByRole("status")).toContainText("saved encrypted");
  await expect(gemini.getByLabel("Gemini API key")).toHaveValue("");
  await expect(gemini.getByLabel("Gemini API key")).toHaveAttribute("placeholder", /Saved securely/);
  await expect(setup.getByRole("button", { name: "Activate draft-only processing" })).toBeDisabled();
  await page.reload();
  await page.getByRole("button", { name: "Business setup", exact: true }).click();
  await expect(page.getByLabel("Company name", { exact: true })).toHaveValue("Acme Services UI");
  await expect(page.getByLabel("Gemini API key")).toHaveValue("");
  await page.getByRole("button", { name: /^Inbox(?:\s+\d+)?$/ }).click();
  await expect(page.getByRole("heading", { name: "Your inbox is clear" })).toBeVisible();
  await page.getByRole("button", { name: "Knowledge", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acme customer account FAQ" })).toBeVisible();
  await expect(page.getByText("Synthetic DEMO-1 document")).toHaveCount(0);
});
