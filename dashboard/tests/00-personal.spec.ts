import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const token = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n").find(line => line.startsWith("OPERATOR_TOKEN="))!.slice("OPERATOR_TOKEN=".length);

test("personal setup is the entry point and explains missing host authorization", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Try your personal inbox" })).toBeVisible();
  await expect(page.getByText("Google sign-in needs hosting setup", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Google", exact: true })).toBeDisabled();
  await expect(page.getByLabel("Google OAuth client secret")).toHaveCount(0);
  await page.getByRole("button", { name: "Open host configuration" }).click();
  await expect(page.getByRole("heading", { name: "Set up your business" })).toBeVisible();
});

test("personal user chooses approved knowledge and a key before explicitly starting drafts", async ({ page }) => {
  const profile = { name: "Personal inbox", support_email: "personal@example.com", acknowledgement: false };
  const setup = { personal: true, personal_available: true, active: false, profile,
    checks: { company_profile: true, approved_knowledge: false, google_verified: true, gemini_verified: false, policy_acknowledged: false },
    connectors: {
      google: { configured: true, verified: true, fields: { mailbox: "personal@example.com" }, secret_fields_set: [] },
      gemini: { configured: false, verified: false, fields: {}, secret_fields_set: [] as string[] },
    } };
  await page.route("**/api/backend/**", async route => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname.split("/api/backend/")[1];
    const method = route.request().method();
    let body: unknown = {};
    if (endpoint === "business") body = setup;
    else if (endpoint === "business/oauth") body = { available: true, google_ready: true };
    else if (endpoint === "personal/drive-folders") body = { folders: [{ id: "folder", name: "Test knowledge" }], has_more: false };
    else if (endpoint === "business/connectors/google" && method === "PUT") Object.assign(setup.connectors.google.fields, { drive_folder_id: route.request().postDataJSON().fields.drive_folder_id });
    else if (endpoint === "business/connectors/google/verify") body = { status: "verified" };
    else if (endpoint === "business/drive/files") body = [{ id: "faq", title: "Personal FAQ", mime_type: "text/plain", revision: "1", modified_time: "today", approved: false }];
    else if (endpoint === "business/drive/files/faq") body = { id: "faq", title: "Personal FAQ", revision: "1", modified_time: "today", content: "Synthetic support hours are Monday to Friday." };
    else if (endpoint === "business/drive/files/faq/approve") {
      const input = route.request().postDataJSON();
      expect(input.owner).toBe("personal@example.com"); expect(input.brand).toBe("Personal inbox"); expect(input.approved).toBe(true);
      setup.checks.approved_knowledge = true;
    } else if (endpoint === "business/connectors/gemini" && method === "PUT") {
      expect(route.request().postDataJSON().fields.gemini_api_key).toBe("synthetic-personal-key");
      setup.connectors.gemini.configured = true; setup.connectors.gemini.secret_fields_set = ["gemini_api_key"];
    } else if (endpoint === "business/connectors/gemini/verify") {
      setup.connectors.gemini.verified = true; setup.checks.gemini_verified = true;
    } else if (endpoint === "business/profile" && method === "PUT") {
      expect(route.request().postDataJSON().acknowledgement).toBe(true); setup.checks.policy_acknowledged = true;
    } else if (endpoint === "business/activate") {
      expect(Object.values(setup.checks).every(Boolean)).toBe(true); setup.active = true;
    } else return route.continue();
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByText("Selected account: personal@example.com")).toBeVisible();
  await page.getByRole("button", { name: "Choose from my Drive folders" }).click();
  await page.getByLabel("Available Drive folders").selectOption("folder");
  await page.getByRole("button", { name: "Use this knowledge folder" }).click();
  await page.getByRole("button", { name: "Browse Google Drive folder" }).click();
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  await expect(page.getByLabel("Drive source knowledge owner")).toHaveCount(0);
  await page.getByLabel("I reviewed this exact version").check();
  await page.getByRole("button", { name: "Approve and import source" }).click();
  await page.getByLabel("Personal Gemini API key").fill("synthetic-personal-key");
  await page.getByRole("button", { name: "Save and verify Gemini" }).click();
  await expect(page.getByRole("button", { name: "Start personal test" })).toBeDisabled();
  await page.getByLabel("I authorize processing this mailbox").check();
  await page.getByRole("button", { name: "Start personal test" }).click();
  await expect(page.getByText("Personal testing active.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Personal Gemini API key")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Pause test" })).toBeEnabled();
});

for (const provider of ["salesforce", "netsuite"]) {
  test(`personal ${provider} button starts a browser-bound PKCE sign-in`, async ({ page, context }) => {
    await page.goto("/");
    await page.getByLabel("Operator access token").fill(token);
    await page.getByRole("button", { name: "Open workspace" }).click();
    const origin = new URL(page.url()).origin;
    const fields: Record<string, string> = { [provider + "_client_id"]: "synthetic-client", [provider + "_client_secret"]: "synthetic-secret" };
    if (provider === "netsuite") fields.netsuite_account_id = "123456_SB1";
    const saved = await page.request.put(`${origin}/api/backend/business/connectors/${provider}`, { headers: { Origin: origin }, data: { fields } });
    expect(saved.ok()).toBe(true);
    await page.reload();
    await page.getByText("Optional: connect Salesforce or NetSuite", { exact: true }).click();
    const name = provider === "salesforce" ? "Salesforce" : "NetSuite";
    let authorization: URL | undefined;
    await page.route(provider === "salesforce" ? "https://login.salesforce.com/services/oauth2/authorize**" : "https://123456-sb1.app.netsuite.com/app/login/oauth2/authorize.nl**", route => {
      authorization = new URL(route.request().url());
      return route.fulfill({ contentType: "text/html", body: "<h1>Mock CRM authorization</h1>" });
    });
    await page.getByRole("button", { name: `Connect ${name}`, exact: true }).click();
    await expect(page.getByRole("heading", { name: "Mock CRM authorization" })).toBeVisible();
    expect(authorization?.searchParams.get("code_challenge_method")).toBe("S256");
    expect(authorization?.searchParams.get("redirect_uri")).toBe(`${origin}/api/oauth/callback/${provider}`);
    const binding = (await context.cookies(`${origin}/api/oauth/callback/${provider}`)).find(cookie => cookie.name === `sf_oauth_${provider}`);
    expect(binding?.httpOnly).toBe(true);
    await page.goto(`${origin}/api/oauth/callback/${provider}?state=${"forged".repeat(8)}&code=invalid`);
    await expect(page.getByRole("status")).toContainText("authorization was not completed");
    expect((await context.cookies(`${origin}/api/oauth/callback/${provider}`)).some(cookie => cookie.name === `sf_oauth_${provider}`)).toBe(false);
  });
}
