import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const env = Object.fromEntries(fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8")
  .split("\n").filter(line => line && !line.startsWith("#") && line.includes("="))
  .map(line => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));

test("guided Google connection uses PKCE and rejects a forged OAuth callback", async ({ page, context }) => {
  await page.goto("/");
  await page.getByLabel("Operator access token").fill(env.OPERATOR_TOKEN);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Set up your business" })).toBeVisible();
  await expect(page.getByText("Using NotebookLM?", { exact: true })).toBeVisible();
  const google = page.locator(".connector-card").filter({ has: page.getByRole("heading", { name: "Google Workspace", exact: true }) });
  await google.getByLabel("Gmail support mailbox").fill("support@acme.example");
  await google.getByLabel("Approved Drive folder").fill("https://drive.google.com/drive/folders/approved-folder");
  await google.getByText("Administrator setup — one time", { exact: true }).click();
  await google.getByLabel("Google OAuth client ID").fill("synthetic-client-id");
  await google.getByLabel("Google OAuth client secret").fill("synthetic-client-secret");
  await google.getByRole("button", { name: "Save connection", exact: true }).click();
  await expect(page.locator(".setup-workspace").getByRole("status")).toContainText("saved encrypted");
  const origin = new URL(page.url()).origin;
  let authorization: URL | undefined;
  await page.route("https://accounts.google.com/o/oauth2/v2/auth**", route => {
    authorization = new URL(route.request().url());
    return route.fulfill({ status: 200, contentType: "text/html", body: "<h1>Mock provider sign-in</h1>" });
  });
  await google.getByRole("button", { name: "Connect Google account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Mock provider sign-in" })).toBeVisible();
  expect(authorization?.searchParams.get("code_challenge_method")).toBe("S256");
  expect(authorization?.searchParams.get("redirect_uri")).toBe(`${origin}/api/oauth/callback/google`);
  expect(authorization?.searchParams.get("access_type")).toBe("offline");
  const binding = (await context.cookies(`${origin}/api/oauth/callback/google`)).find(cookie => cookie.name === "sf_oauth_google");
  expect(binding?.httpOnly).toBe(true);
  expect(binding?.sameSite).toBe("Lax");
  await page.goto(`${origin}/api/oauth/callback/google?state=${"forged".repeat(8)}&code=invalid-code`);
  await expect(page.getByRole("heading", { name: "Set up your business" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("authorization was not completed");
  expect((await context.cookies(`${origin}/api/oauth/callback/google`)).some(cookie => cookie.name === "sf_oauth_google")).toBe(false);
});
