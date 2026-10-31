# Automatic customer-support replies and CRM updates

SupportFlow connects to your existing business workflow. It can send eligible Gmail support replies using approved knowledge, then independently log confirmed delivery against the customer and support case in Salesforce and/or NetSuite. It does not replace your helpdesk, close cases, issue refunds, or alter customer account/financial details.

## Configure once, authorize accounts, choose the reply policy

1. Deploy the latest commit. **Company workspace** keeps the business setup and connectors; **Personal test environment** has separate credentials, messages, knowledge, queues and policy.
2. The host registers OAuth applications once and configures their client IDs/secrets. Google requires Gmail/Drive APIs and the exact callback for the selected environment. Company: `/api/oauth/callback/google`; personal test: `/api/oauth/callback/test/google`. Registered host credentials enable the Connect buttons without entering client credentials per account. Company Google sign-in uses the support mailbox in the saved company profile; personal sign-in discovers the selected primary Gmail automatically.
3. Connect Google. Select your Drive folder, preview and approve the exact source versions. Save and verify your Gemini key/model. Google SSO alone does not supply Gmail authorization to an unregistered application; ChatGPT's Google connection is not the application's credential.
4. Connect Salesforce/NetSuite if required. Verify their access and configure the permissions below. These providers are optional for an email-only personal test.
5. In **Automatic replies and CRM updates**, select automatic sending, set an hourly limit, choose the CRM destinations, and explicitly acknowledge sending/record writes. For personal testing enter the exact email address of your second sender account; the backend requires this allowlist. An empty company allowlist permits incoming senders subject to all other checks.
6. Save the reply policy. This pauses processing. Finish readiness and use **Activate automatic replies** in company setup or **Start automatic email test** in personal setup. Draft review remains available by disabling automatic mode, saving, then activating the draft policy.
7. Send a fresh question from the allowed second account **after activation**. Inspect the answer in its receiving inbox, Gmail Sent, and the CRM delivery table. Saving/re-activating starts a new automation window; older messages are excluded from automatic processing rather than receiving delayed replies.

## Which questions send automatically?

The supported automatic categories are approved manual links, setup FAQs and product specifications. The proposal must be certain, use current approved source quotes/revisions, have a known model/general knowledge scope, and pass recipient/thread/loop/risk checks. Unknown, unsupported-language, safety, refund/complaint, business escalation, prompt injection, uncertain or ungrounded cases remain for human handling. The model does not receive CRM data or tools for modifying records.

Exact source quotes establish traceability, not a proof that all generated prose follows from them. Test your business's answer quality and escalation policies before enabling actual customer automation. The deterministic manual-link path remains available; new opt-in FAQ automation can send model prose. No factual-correctness certification is claimed.

Only messages with Google's trusted API `internalDate` on or after the current activation time can enter this new automatic mode. Sender-provided copies of that internal timestamp are discarded by the Gmail adapter. Older/out-of-scope messages are excluded without model calls, draft creation or sends. No automatic backlog replay occurs after pausing/reactivating. Existing draft-only and legacy template behavior remains unchanged when the new policy is disabled.

## Human handling when the assistant cannot safely answer

Configured-business risk, uncertainty and missing grounding pause that conversation and queue an internal email to the configured escalation contact. CRM ambiguity, uncertain writes and exhausted retries also notify the team. The **Handoffs** screen shows the reason, notification state and explicit resume action. [Human handoff setup and recovery](HUMAN_HANDOFF.md) describes deduplication, delivery verification and notification limits. Pending notifications and CRM logging continue when customer processing is paused.

## Confirmed delivery, then customer activity and support case

Automatic sending has its own durable job. A draft is verified for recipient, text and threading immediately before a send reservation is persisted. A crash or timeout after reservation does not authorize another send. Use Gmail reconciliation to confirm an uncertain send; CRM work is created only after confirmation.

Each selected provider gets an independent durable CRM job, keyed by provider and incoming message. The CRM resolves exactly one customer by the real sender's email. A numeric `Case #123`, `Case: 123` or `Ticket #123` reference in the subject can narrow the case search, always scoped to that matched customer. Multiple references are held for review. Without a reference, Salesforce requires exactly one open case for the Contact; NetSuite requires exactly one matching case for the customer. The case/customer relationship is checked again immediately before each write. Missing/ambiguous matches are not guessed, and no new customer/case is automatically created.

Email matching is not independent customer identity verification. These lookups support internal delivery logging; never treat them as authorization to disclose private account information.

### Salesforce

Provide an OAuth integration user with API access, Contact and Case read access, and **Task** and **CaseComment** create permission. Configure `api`, `refresh_token`, `openid` scopes and the appropriate environment callback. Describe metadata is checked before enabling writes and before syncing.

- Customer activity: a standard completed Task linked by `WhoId` to the Contact and `WhatId` to the Case, with the sent response, Gmail delivery ID, outcome and deterministic delivery marker in its description.
- Case update: a private `CaseComment` (`IsPublished=false`) on that Case. No case status is changed and no Salesforce email-send API is invoked.

This adapter targets standard Contact-linked Cases and the standard Task `Completed` status. Custom identity objects, custom activity status values, Salesforce person-account routing or different field schemas need an explicit adapter/mapping extension. The case comment is bounded to 4,000 characters; the customer Task retains the longer bounded reply log.

### NetSuite

Use an OAuth2 integration and a role with Customer/Support Case read, SuiteQL, metadata, Task creation and Support Case edit access. The adapter validates the live REST JSON schemas before enabling writes. Its Task fields must expose writable `title`, `company`, `message` properties.

Create or select a dedicated **custom text field on support cases**, for example `custevent_supportflow_last_reply`. Enter its script ID in the NetSuite connector or automation form. This is a real account-side requirement; the application does not silently create ERP schema fields. Its live metadata must expose that field as a writable string.

- Customer activity: a standard Task attached to the customer, containing the sent reply, case ID, Gmail delivery ID and delivery marker.
- Case update: PATCH only that dedicated case-reply field with the latest processed delivery log, bounded to 10,000 characters. Existing case text/status and customer details remain unchanged. The field represents the last processed log, not a complete conversation history; customer Tasks retain individual delivery logs.

The adapter does **not** set `outgoingMessage`, request another NetSuite email, close the case or modify accounting transactions. Schemas, field lengths, feature availability and permissions must be checked in your actual NetSuite sandbox. Unsupported metadata fails before a CRM mutation. NetSuite licenses/free availability are not supplied by this repository.

## Retries, manual case mapping and uncertain operations

The delivery table shows separate customer-activity and case states. Transient failures before an external write retry with bounded backoff; five failed attempts require attention. Successful activity work is retained if later case processing fails. CRM retries run independently of mailbox processing and never send email again. Disabling a selected CRM stops its pending updates; pausing email processing alone still allows already confirmed deliveries to finish logging.

For a missing/ambiguous case, enter its existing CRM record ID in the delivery row. The backend verifies ownership by the matched customer before queueing it. It cannot remap a completed activity to another case. A record number shown to customers can differ from the provider's internal record ID; manual mapping expects the internal ID.

A timeout/crash during a POST/PATCH is held as an uncertain external write. **Retry CRM update** cannot repeat it. Inspect the CRM, enter the actual Task/CaseComment record ID and choose **Verify existing external write**. The backend reads the external record and checks the delivery marker and customer/case relationship. NetSuite case reconciliation checks its configured field on the known case. A successful check marks only the confirmed stage complete and queues any remaining work. Absence, a wrong record, changed organization or a missing marker leaves it held. There is no force-repeat button for uncertain writes.

The active job lease and SQL row locks coordinate workers. Remote providers and PostgreSQL do not share a transaction; a narrow configuration/pause window can still exist around already-started external requests. Watch operations and provider roles, and preserve the stable encryption key across deploys. Personal testing uses its own storage/encryption context but shares hosting and operator access with the company area.

## Test before business use

Use a test Gmail and a second account you control. Register its OAuth client/test user, add synthetic FAQs, enable automatic mode only for the second sender and activate. Send one new question; verify exactly one reply, actual receipt and Gmail Sent. With sandbox CRMs selected, verify one customer activity and one case update per provider. Exercise ambiguity, a missing case, paused processing, expired credentials, provider downtime, uncertainty reconciliation and company/test isolation.

Automated tests use controlled Gmail/model/CRM contracts and cannot establish a live grant, role permissions, model quality or delivery for your accounts. No live customer email or CRM write is claimed until you complete those account tests. Free Render sleep pauses timely processing; use continuously available hosting before relying on unattended support response times.
