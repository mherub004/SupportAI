import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const token = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n").find(line => line.startsWith("OPERATOR_TOKEN="))!.slice("OPERATOR_TOKEN=".length);

test("personal user explicitly selects automatic replies, sender scope and CRM logging", async ({ page }) => {
  let saved: Record<string, unknown> | undefined;
  const mutations: string[] = [];
  await page.route("**/api/backend/automation**", async route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") mutations.push(url.pathname);
    if (url.pathname.endsWith("/automation")) {
      if (route.request().method() === "PUT") {
        saved = route.request().postDataJSON();
        expect(route.request().headers()["x-supportflow-workspace"]).toBe("test");
        return route.fulfill({ json: { status: "saved", activation_required: true } });
      }
      return route.fulfill({ json: { enabled: false, acknowledgement: false, allowed_senders: [], hourly_limit: 10, crm_providers: [] } });
    }
    if (url.pathname.endsWith("/retry")) return route.fulfill({ json: { status: "queued", email_resend: false } });
    return route.fulfill({ json: [{ message_id: "confirmed-message", provider: "salesforce", activity_state: "done", case_state: "pending", status: "failed", error: "TimeoutError", case_id: "500000000000001" }] });
  });
  await page.goto("/?workspace=test");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "Automatic replies and CRM updates", exact: true }) });
  await panel.getByLabel("Automatically send eligible support replies").check();
  await panel.getByLabel("Allowed test sender emails").fill("second-account@example.com");
  await panel.getByLabel("Maximum replies per hour").fill("3");
  await panel.getByRole("checkbox", { name: "Salesforce", exact: true }).check();
  await expect(panel.getByRole("button", { name: "Save reply automation" })).toBeDisabled();
  await panel.getByLabel("I authorize automatic email sending").check();
  await panel.getByRole("button", { name: "Save reply automation" }).click();
  await expect(panel.getByRole("status")).toContainText("Processing is paused");
  expect(saved).toEqual({ enabled: true, acknowledgement: true, allowed_senders: ["second-account@example.com"], hourly_limit: 3, crm_providers: ["salesforce"] });
  await panel.getByRole("button", { name: "Retry CRM update" }).click();
  await expect(panel.getByRole("status")).toContainText("Email will not be resent");
  expect(mutations).toEqual(["/api/backend/automation", "/api/backend/automation/deliveries/confirmed-message/salesforce/retry"]);
});

test("uncertain CRM writes require external verification instead of a blind retry", async ({ page }) => {
  let verified = false;
  await page.route("**/api/backend/automation**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/automation")) return route.fulfill({ json: { enabled: false, acknowledgement: false, allowed_senders: [], hourly_limit: 10, crm_providers: [] } });
    if (url.pathname.endsWith("/reconcile")) {
      expect(route.request().postDataJSON()).toEqual({ external_id: "00a000000000001" });
      verified = true;
      return route.fulfill({ json: { status: "confirmed" } });
    }
    return route.fulfill({ json: [{ message_id: "uncertain", provider: "salesforce", activity_state: "done", case_state: verified ? "done" : "reserved", status: verified ? "done" : "needs_review", error: verified ? "" : "UncertainExternalWrite", case_id: "500000000000001" }] });
  });
  await page.goto("/?workspace=test");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("button", { name: "Retry CRM update" })).toHaveCount(0);
  await page.getByLabel("External CRM record ID for salesforce:uncertain").fill("00a000000000001");
  await page.getByRole("button", { name: "Verify existing external write" }).click();
  await expect(page.getByRole("status")).toContainText("No email was resent");
  expect(verified).toBe(true);
});
