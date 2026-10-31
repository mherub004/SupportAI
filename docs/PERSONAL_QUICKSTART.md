# Personal setup: Google, knowledge and a Gemini key

The default **Company workspace** keeps all company forms, policies and connectors. Click **Personal test environment** beside it, then **Personal setup**, for your separate Gmail trial. Switching environments never replaces the company profile.

1. Click **Connect Google**, choose one Gmail account and grant access. The application discovers the actual primary mailbox from Google's API and creates a paused personal profile automatically. No mailbox address, OAuth token or company details need to be entered by the account user.
2. Click **Choose from my Drive folders**, choose a folder and **Use this knowledge folder**. A folder URL/ID also works. The selector lists up to 100 accessible folders; paste a link for one not listed. Only supported direct-child documents can be imported.
3. Browse the folder, preview a document, choose its language and explicitly approve its exact version. Personal setup supplies the knowledge family, general model and owner automatically. This does not change Drive sharing or approve future revisions. Existing approved knowledge imported through the authenticated API is also usable.
4. Enter your own **Gemini API key** and available model, then **Save and verify Gemini**. The key is encrypted and never returned to the browser after saving; blank preserves an existing key.
5. Review the processing acknowledgement and click **Start personal test**. Send a fresh question from a second account, inspect the app's Inbox and Gmail Drafts, edit/approve if appropriate, then send manually in Gmail. **Pause test** stops new worker processing; an already-started request can finish.

Use a dedicated test mailbox different from the company mailbox, so two workers do not process the same external inbox. The first reconciliation reads the last seven days of inbox mail, and later history sync can ingest other newly added messages; there is no test-sender allowlist. Model usage and free hosting limits still apply. Application sending remains disabled; a manual Gmail send does not automatically update the app's sent state.

## One-time hosting requirement

A Google sign-in button requires a Google OAuth Web client owned/configured by the host. It cannot use ChatGPT's Google connection, a Gemini key, or invented credentials. Configure these **server-side environment variables** on Render (or your backend host):

```text
GOOGLE_CLIENT_ID=<your registered OAuth Web client ID>
GOOGLE_CLIENT_SECRET=<your registered client secret>
```

Register the exact callback displayed in Personal setup. The test callback is `https://supportflow-demo.onrender.com/api/oauth/callback/test/google`. Keep the company callback `https://supportflow-demo.onrender.com/api/oauth/callback/google` registered too if company sign-in is used. Enable Gmail/Drive APIs, declare Gmail modify and Drive readonly scopes, and configure the Google consent audience/test users. For a private personal test, an External/Testing client with the selected Gmail added as a test user is sufficient subject to Google's account policies. Public distribution may require Google's app verification and additional privacy/security review.

Once these host settings exist and the service restarts, users only need the Google consent screen. The company’s saved administrator configuration remains in the company area and is not copied into the test area. Use the server-side client settings to enable test sign-in. An incomplete saved client can fall back to the host's configured pair; a complete saved pair takes precedence. The status API reports readiness as a boolean and never returns the host secret. A missing client is shown explicitly in Personal setup and Connect stays disabled. It is a real deployment prerequisite, not an extra Gemini setting.

The same operator session can access both environments; they are not separate user roles or a public multi-user login service. PostgreSQL uses `supportflow_personal_test` for test tables while company tables remain in their existing schema. SQLite development uses a separate sibling file. Test connector encryption uses a distinct key derived from the stable deployment key. The test API and worker use only test storage, and API requests specify their environment per browser tab. No company mailbox tokens, Gemini key, selected folder, messages or knowledge are copied. After a live mailbox is used, its identity stays fixed within that environment.

Render starts both APIs and workers automatically. Compose and the development script do the same. A custom dashboard needs `TEST_API_URL` pointing to its separately running test API (`app.main:create_test_app`); the test worker runs with `python -m app.worker --personal-test`. Missing test API configuration disables the switch and fails closed rather than forwarding test requests to company storage. An optional `PERSONAL_TEST_DATABASE_URL` puts test tables on another database; otherwise no second hosted database is required. PostgreSQL initialization needs permission to create the fixed test schema. The two areas share the hosting service, operator access, database server by default, and resource/failure limits; this is logical data isolation, not an independent production security boundary.

Connection credentials are encrypted using the existing stable deployment key. PKCE, one-time browser-bound OAuth state, profile/configuration fingerprints, mailbox-origin checks, readiness and explicit activation remain in force. A cancelled/failed sign-in does not create an active profile. Google verification is valid for 24 hours when activating; selecting another folder pauses processing and verifies access again. Test-mode Google refresh grants can expire and require reconnecting.

For detailed provider registration see [the Google test guide](PERSONAL_TEST.md). For reply quality, source changes, escalation, job handling and optional CRM tests, use its 30-function checklist. Automated fixtures are not evidence of a real account connection.

## Optional CRM sign-in buttons

Expand **Optional: connect Salesforce or NetSuite** to connect, verify or disconnect each provider without filling its administrator form. After verification, open a Gmail message and load its read-only CRM context. Failing or disconnecting a CRM does not stop Gmail drafting.

The host can configure `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET` and optionally `SALESFORCE_LOGIN_URL`. For NetSuite use `NETSUITE_CLIENT_ID`, `NETSUITE_CLIENT_SECRET` and `NETSUITE_ACCOUNT_ID`. A saved complete client configuration takes precedence within its own environment. The account ID is needed before NetSuite can show its account-specific sign-in screen; an integration registered for one account is not a universal connector for every customer's NetSuite account. Provider authorization policies and the user's permissions still apply. Test callbacks are `/api/oauth/callback/test/salesforce` and `/api/oauth/callback/test/netsuite` on the dashboard origin; company callbacks omit `/test`. Register the correct URLs and follow [the provider registration guide](INTEGRATIONS.md).

These are OAuth authorization-code/PKCE connections with encrypted token storage. Salesforce/NetSuite remain read-only standard customer lookups; no write/order/refund functionality is added. The buttons do not create provider accounts or provision/register OAuth clients. Missing host settings leave the corresponding button disabled with an explanation.
