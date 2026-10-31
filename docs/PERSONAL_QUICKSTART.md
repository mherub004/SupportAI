# Personal setup: Google, knowledge and a Gemini key

Open **Personal setup**, now the default workspace screen. Company forms and CRM settings remain separately accessible in **Business setup**.

1. Click **Connect Google**, choose one Gmail account and grant access. The application discovers the actual primary mailbox from Google's API and creates a paused personal profile automatically. No mailbox address, OAuth token or company details need to be entered by the account user.
2. Click **Choose from my Drive folders**, choose a folder and **Use this knowledge folder**. A folder URL/ID also works. The selector lists up to 100 accessible folders; paste a link for one not listed. Only supported direct-child documents can be imported.
3. Browse the folder, preview a document, choose its language and explicitly approve its exact version. Personal setup supplies the knowledge family, general model and owner automatically. This does not change Drive sharing or approve future revisions. Existing approved knowledge imported through the authenticated API is also usable.
4. Enter your own **Gemini API key** and available model, then **Save and verify Gemini**. The key is encrypted and never returned to the browser after saving; blank preserves an existing key.
5. Review the processing acknowledgement and click **Start personal test**. Send a fresh question from a second account, inspect the app's Inbox and Gmail Drafts, edit/approve if appropriate, then send manually in Gmail. **Pause test** stops new worker processing; an already-started request can finish.

Use a dedicated test mailbox. The first reconciliation reads the last seven days of inbox mail, and later history sync can ingest other newly added messages; there is no test-sender allowlist. Model usage and free hosting limits still apply. Application sending remains disabled; a manual Gmail send does not automatically update the app's sent state.

## One-time hosting requirement

A Google sign-in button requires a Google OAuth Web client owned/configured by the host. It cannot use ChatGPT's Google connection, a Gemini key, or invented credentials. Configure these **server-side environment variables** on Render (or your backend host):

```text
GOOGLE_CLIENT_ID=<your registered OAuth Web client ID>
GOOGLE_CLIENT_SECRET=<your registered client secret>
```

Register the exact callback displayed in Business setup. For the current deployment it is `https://supportflow-demo.onrender.com/api/oauth/callback/google`. Enable Gmail/Drive APIs, declare Gmail modify and Drive readonly scopes, and configure the Google consent audience/test users. For a private personal test, an External/Testing client with the selected Gmail added as a test user is sufficient subject to Google's account policies. Public distribution may require Google's app verification and additional privacy/security review.

Once these host settings exist and the service restarts, users only need the Google consent screen. The old encrypted administrator-client configuration is also supported. An incomplete saved client can fall back to the host's configured pair; a complete saved pair takes precedence. The status API reports readiness as a boolean and never returns the host secret. A missing client is shown explicitly in Personal setup and Connect stays disabled. It is a real deployment prerequisite, not an extra Gemini setting.

The operator access token still protects the workspace. Connecting Google authorizes the mailbox; it does not turn this into a multi-user signup/login service. An unfinished business profile with no live mail can be replaced through the confirmed personal sign-in flow. Installations with live business mail cannot switch to personal mode. After personal mail is ingested, another mailbox is rejected: use a separate deployment/database for a company or another account.

Connection credentials are encrypted using the existing stable deployment key. PKCE, one-time browser-bound OAuth state, profile/configuration fingerprints, mailbox-origin checks, readiness and explicit activation remain in force. A cancelled/failed sign-in does not create an active profile. Google verification is valid for 24 hours when activating; selecting another folder pauses processing and verifies access again. Test-mode Google refresh grants can expire and require reconnecting.

For detailed provider registration see [the Google test guide](PERSONAL_TEST.md). For reply quality, source changes, escalation, job handling and optional CRM tests, use its 30-function checklist. Automated fixtures are not evidence of a real account connection.

## Optional CRM sign-in buttons

Expand **Optional: connect Salesforce or NetSuite** to connect, verify or disconnect each provider without filling its administrator form. After verification, open a Gmail message and load its read-only CRM context. Failing or disconnecting a CRM does not stop Gmail drafting.

The host can configure `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET` and optionally `SALESFORCE_LOGIN_URL`. For NetSuite use `NETSUITE_CLIENT_ID`, `NETSUITE_CLIENT_SECRET` and `NETSUITE_ACCOUNT_ID`. A saved complete client configuration takes precedence. The account ID is needed before NetSuite can show its account-specific sign-in screen; an integration registered for one account is not a universal connector for every customer's NetSuite account. Provider authorization policies and the user's permissions still apply. Register the corresponding callback URLs shown in Business setup and follow [the provider registration guide](INTEGRATIONS.md).

These are OAuth authorization-code/PKCE connections with encrypted token storage. Salesforce/NetSuite remain read-only standard customer lookups; no write/order/refund functionality is added. The buttons do not create provider accounts or provision/register OAuth clients. Missing host settings leave the corresponding button disabled with an explanation.
