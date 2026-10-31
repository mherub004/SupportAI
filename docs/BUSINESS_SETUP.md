# Deploy once, configure the business later

For the automatic email → customer activity → support case workflow, follow [AUTOMATION.md](AUTOMATION.md). Draft review remains the default; the older draft-only/read-only descriptions below describe that default mode.

Testing before handing this to a company? Follow [the personal Gmail test guide](PERSONAL_TEST.md) in a separate test installation; it includes the one-time Google setup and a function checklist.

SupportFlow can be deployed before any Google accounts, business knowledge or model keys are connected. The authenticated application opens **Company workspace → Business setup** with all business connectors. A separate [Personal test environment](PERSONAL_QUICKSTART.md) is available beside it without replacing the company profile or copying company credentials. Each company uses a separate deployment, PostgreSQL database, operator token and connector credentials. This release is not a public shared multi-tenant signup service.

## Company onboarding

1. Sign in using the deployment's `OPERATOR_TOKEN` from Render Environment settings.
2. Save the company name, industry, website, support mailbox, escalation contact, supported English/German languages, response tone and business-specific human-review keywords. Saving pauses processing. The acknowledgement records your responsibility to review the provider's data-processing terms and your authority to connect company data.
3. Add reviewed knowledge from the setup form. Business/product family is configurable and no longer restricted to ABL/Wallbox. Use the company name and model `general` for company-wide FAQs/policies; use canonical product/model names for product-specific sources. Only approved, effective, customer-safe sources participate. Retire a manual source from Knowledge when obsolete; old replies referencing it fail source checks. Manage Drive approval at the Drive source and synchronize it.
4. Connect **Google Workspace** with an administrator-approved user mailbox and OAuth refresh credentials, or a short-lived test access token. An approved Drive folder and Pub/Sub settings are optional. Shared Google Groups are not supported as Gmail user mailboxes. Use the guided account connection after the one-time OAuth client setup. The app is not a preverified public marketplace OAuth client; your administrator controls registration/consent. See INTEGRATIONS.md.
5. Connect **Gemini** using an approved model/key. Save and verify both provider connections. Tests make read-only profile/folder/model requests, with no customer emails sent and no email content sent to Gemini during verification. A successful model lookup proves access, not real-world response quality.
6. Resolve every readiness item and choose **Activate draft-only processing**. Activation reads the configured inbox and passes bounded plain-text messages and approved source context to Gemini. Choose this only after privacy approval and testing. No app-generated email is sent: business setup enforces draft-only processing, regardless of automatic-send environment flags.

Configuration changes are picked up by the API/worker without redeploying. Saving profile or connector changes pauses processing. Changed credentials require a new verification; verification must be no older than 24 hours when activating. Existing in-flight requests can finish during a pause. The Gmail polling worker must be continuously running for timely processing; a sleeping free Render service is appropriate for a demo only.

## Credentials

Connector credentials are encrypted in PostgreSQL with Fernet authenticated encryption, and never returned by the setup API or included in audit details. The browser only receives non-secret fields and which secret fields are configured. Blank secret inputs preserve existing credentials; Disconnect removes that connector's encrypted record and pauses processing. Backups and administrator access still require protection.

By default the encryption key is derived from the existing high-entropy `OPERATOR_TOKEN`. Keep that token stable across deployments. Optionally set a separate random `CONNECTOR_ENCRYPTION_KEY` (at least 32 characters) **before saving the first connection**. Changing the key or fallback operator token after saving credentials makes them unreadable; plan a credential migration or disconnect and securely re-enter them before rotation. Never paste real secrets into Git or chat.

## Isolation and upgrade behavior

The upgrade adds configuration, connector and message-origin tables without altering or deleting existing message/source tables. Existing synthetic records remain in the database but are hidden from a configured business and cannot be sent through a live connector. Startup stops reseeding an installation once a business profile exists.

Messages are bound to their originating provider/mailbox. Once live messages exist, this installation's mailbox identity cannot be reassigned to another company. Use a separate deployment/database instead. Unclassified pre-upgrade live records require an explicit identity migration before activation; the app fails closed rather than guessing ownership. Individual user accounts, RBAC and shared multi-company hosting are still separate production work.

## Scope

Available connectors: Gmail, Google Drive, Gemini, manual knowledge, and optional read-only Salesforce/NetSuite customer lookup. Microsoft 365, Shopify and WhatsApp are explicitly unavailable. There is no claim that an arbitrary third-party service can connect or that one policy is safe for every industry. Medical, financial, legal and other regulated workflows require specialist review and additional policies. Escalations show the configured human contact; the app does not automatically create tickets or forward sensitive cases.

Current languages are English and German. Grounded drafts remain subject to human factual/safety review. Deploying this template does not confer privacy approval or authorize automatic replies. Use always-on hosting, enterprise authentication, backups and monitoring before handling real customer data.

## Development verification

The browser suite includes onboarding mutations. Run it only against a disposable, initially unconfigured demo database; it creates a fictional company profile and dummy encrypted connector setting, hides retained synthetic inbox data, and leaves processing paused. It never verifies the dummy provider key or sends mail. Do not target a live company installation with these tests. Backend tests use isolated temporary databases and mocked provider checks.

The preferred Drive setup now uses Browse → Preview → Approve for an exact source version; no manual Drive appProperties edits are required. See [the integration guide](INTEGRATIONS.md).
