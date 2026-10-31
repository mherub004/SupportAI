# Security boundaries and production gates

This code is a single-organization pilot. It is not a multi-tenant SaaS, a certified electrical-safety system, or a completed commercial product.

## Controls implemented

- Authenticated API; constant-time operator token comparison; no browser-embedded backend credential. Next.js stores an HttpOnly, same-site, one-hour session cookie and checks origin on state-changing requests.
- Secure cookies by default in code. The generated local `.env` explicitly disables Secure for loopback HTTP; restore `COOKIE_SECURE=true` before using HTTPS/nonlocal access.
- Backend kill switch starts on. Automatic replies also require two explicit server settings, deterministic category/grounding checks and no human ownership.
- Draft review is the default. Explicitly enabled automation can send eligible grounded/certain FAQ and product-specification prose as well as approved manual links. Risk-tagged, uncertain and ungrounded cases remain blocked. Personal automatic tests require an exact sender allowlist and only newly received mail can enter the new automation mode.
- Source approval/classification, effective/expiry dates, revision/checksum/customer-link rechecks and bounded scope. Unknown/mixed product routing fails closed.
- Message IDs and send reservations protect retry behavior. Drafts are verified immediately before sending, including recipient, sender, threading headers, body and absence of CC/BCC.
- Google JWT push verification; no unauthenticated operator mutations. General exceptions return a generic error; worker/audit store error types rather than provider response bodies.
- Secrets are ignored by Git. Containers run as non-root. The database has no published port. Default published app ports are loopback only.

## Limits requiring production work

1. **SSO/RBAC:** the pilot uses one shared operator token, not individual accounts or roles. Deploy behind your corporate SSO/access gateway and firewall, then integrate verified per-user identity and attributable audit events before production. Audit actor `operator` is not a verified named person. No login brute-force limiter is built in; enforce one at the gateway.
2. **Safety:** regex classifiers are intentionally conservative, incomplete heuristics. The synthetic safety tests do not prove absence of critical errors on actual customer messages. Human specialist routing, approved fixed safety wording, multilingual adversarial evaluation and signed go-live gates are mandatory. The generic escalation draft gives no electrical instructions.
3. **Grounding:** exact source quotes prove traceability, not that arbitrary model prose is entailed by those quotes. The original default/template mode retains its fixed-link restriction. Opt-in FAQ automation permits model prose and requires business-specific answer-quality testing; exact quotation checks do not certify that prose is entailed by its evidence.
4. **Race window:** Gmail and SQL do not share a transaction. A human can intervene or edit a draft between the final external check and Gmail's send request. Pause rules and kill switches govern new reservations, not an already in-flight request. Resolve the operational handoff policy and external-send coordination before live automation.
5. **Data:** customer email bodies and source content are stored in the database, unencrypted at the application layer. Use encrypted storage, restricted DB access, backups, approved retention and a secret manager. Full PII redaction, attachment malware scanning, DLP, key rotation orchestration and data residency enforcement are not supplied.
6. **Audit:** the audit table is operational evidence, not an immutable tamper-proof compliance ledger. Free-text operator review reasons may contain personal data; instruct operators accordingly and apply retention/access policy.
7. **Google identity:** provider-based OAuth consent is supported after administrator client registration, but public-app verification is not supplied. Use an administrator-approved test identity. No financial account changes, refunds or warranty decisions are implemented. Opt-in confirmed-delivery logging can create customer activities and update support cases using the restricted adapters described in AUTOMATION.md; email matching is not proof of identity.
8. **Authorization of knowledge:** appProperties approval is metadata written by trusted owners, not a separate signed approval workflow. Do not grant untrusted people write access to that metadata or import API.
9. **Content isolation:** email/documents are untrusted model context. Prompts and policy gates reduce injection exposure but do not constitute a comprehensive injection defense. There is no tool execution from model output.
10. **Dependencies and deployment:** run routine security scanning and updates, enforce HTTPS/access logs without secret headers, configure ingress/body limits, and review cloud IAM. Default localhost deployment is not an internet-facing hardened service.

Never use company assets for commercial distribution without the plan's employer/IP and licensing approval. This repository includes only deliberately fictional sample content.

## Business configuration update

The setup API requires the same authenticated operator access as other administrative actions. Connector credentials are Fernet-encrypted; API/audit responses reveal configuration status and non-secret fields only. A separate CONNECTOR_ENCRYPTION_KEY can be set before initial configuration; otherwise OPERATOR_TOKEN derives the key. Key rotation requires a planned credential migration or secure re-entry.

Business setup starts draft-only. An authenticated, explicitly acknowledged automation policy can enable eligible automatic replies after readiness and activation. Saving policy changes pauses processing; personal automatic tests require an exact test-sender allowlist. Connection verification is required before activation; changes pause processing. Each deployment/database belongs to one company, and a live mailbox identity cannot be reassigned through the setup UI. Existing pre-upgrade messages without provider identity cannot be processed by live connectors. This adds setup controls; it does not implement shared tenant hosting or replace enterprise SSO.

## OAuth, Drive and CRM extension

Browser-bound PKCE authorization sessions expire after ten minutes and are consumed before code exchange. Credentials stay encrypted; rotating CRM refresh tokens are persisted before further API calls. Callback origins and provider hostnames are constrained. UI-managed Drive approvals bind revision and modified time and cannot be silently reused after a detected change. Exact citations are checked against full original content as well as bounded excerpts.

Salesforce/NetSuite customer lookup is an explicit reviewer action for real company Gmail records. It uses fixed read-only queries, handles ambiguity without candidate disclosures, and never feeds CRM facts to Gemini. Separately selected automation destinations can write a confirmed sent-email activity and case log; these writes have their own durable states and never retry email sending. Email matching is not identity verification. Provider roles must themselves be least privilege. See INTEGRATIONS.md for authorization and logging requirements.
