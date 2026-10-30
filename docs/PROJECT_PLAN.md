Prepared for: Project Manager, Customer Support, IT/Security and Product Stakeholders

Version 1.0 \| Status: Proposal / approval required \| Date: 30 October 2026

# Executive decision summary

Approve a phased project to deliver a Gemini-powered, knowledge-grounded customer email agent for the ABL/Wallbox support environment. Initially the system reads from a designated Google Workspace Gmail mailbox and approved Google Drive documents, drafts accurate responses, and ultimately auto-sends only permitted low-risk replies after measurable validation. The existing chatbot and ticket system remain in place for escalation. The underlying application is packaged as a reusable, self-hosted product with configurable connectors, enabling potential later commercialization subject to employer/IP approvals.

| Decision requested | Proposal                                                                                                           |
|--------------------|--------------------------------------------------------------------------------------------------------------------|
| Pilot scope        | Email only; Gmail + Google Drive + Gemini; German and English; approved EV charger support documentation.          |
| Delivery model     | Internal deployment first; design modular connectors and Docker packaging for future self-hosted licensing.        |
| Approval gates     | Security/privacy review, approved knowledge, technical evaluation, supervised pilot and explicit go-live sign-off. |
| Excluded initially | Phone calls, public SaaS, generalized CRM actions, refunds, warranties decisions, electrical repair instructions.  |

# 1. Business case and objectives

Problem: support agents spend time finding technical documentation, answering repeated setup/manual questions, requesting missing charger details, and handling simple follow-up emails. The company already has ticket-opening capabilities, so duplicating ticketing would add cost without addressing the immediate bottleneck.

- Primary goal: reduce manual handling time for email inquiries without reducing response correctness or safety.

- Secondary goal: improve response consistency across ABL and Wallbox product families and German/English language cases.

- Strategic goal: retain reusable product code, pluggable providers and repeatable deployment for a future commercial edition.

- Non-goal: guarantee full automation of all support inquiries; specialist and safety-critical cases remain human-owned.

# 2. Scope and deliverables

| In scope — internal pilot                                         | Out of scope — first release                                    |
|-------------------------------------------------------------------|-----------------------------------------------------------------|
| Knowledge sync from approved Google Drive Shared Drive/folder     | NotebookLM generated chat content as production source of truth |
| Gemini response generation with retrieved document evidence       | Training a proprietary foundation model                         |
| Gmail message ingest, thread tracking, drafts and controlled send | Phone calling / telephony system                                |
| Brand/model routing, clarification requests, escalation           | Live CRM/ERP mutations, refunds or account changes              |
| Operator review screen, logs, analytics, operational controls     | Customer-facing web chatbot replacement                         |
| Dockerized app and connector interfaces                           | Instant compatibility with any arbitrary third-party API        |

# 3. Stakeholders and responsibilities

| Role                                 | Accountability                                                                             |
|--------------------------------------|--------------------------------------------------------------------------------------------|
| Executive sponsor / support director | Business outcomes, production authorization, escalation policy.                            |
| Project manager / product owner      | Scope, backlog, sprint plan, acceptance, dependencies and communications.                  |
| Support subject-matter experts       | Knowledge validation, evaluation examples, escalation categories.                          |
| Engineering lead / backend developer | Gmail ingestion, AI orchestration, connectors, data model, testing.                        |
| Cloud / DevOps engineer              | GCP projects, deployment, CI/CD, observability, recovery.                                  |
| Security / privacy / legal           | Data processing approval, restricted OAuth scopes, retention, vendor review, IP ownership. |
| QA / evaluation owner                | Test dataset, error analysis, regression, pilot performance reports.                       |

# 4. Target user journeys

1.  Support manager configures the approved knowledge folder, Gmail mailbox, agent policies and escalation contacts.

2.  Customer emails the support mailbox; system receives notification, fetches the latest Gmail history and identifies the actual message.

3.  Agent detects language, ABL vs Wallbox product, model/error and whether sufficient facts exist.

4.  Retriever returns only current, approved, customer-safe knowledge; Gemini proposes structured intent, supporting evidence and response.

5.  Policy layer either creates a human-review draft, auto-sends an eligible reply, or routes to an existing support path.

6.  Follow-up customer email resumes the same Gmail thread; human intervention pauses AI sending.

7.  Manager reviews correction reasons, unresolved topics, automation rate and verified resolution rate.

# 5. Solution architecture

Logical flow: Gmail API / Pub/Sub → authenticated webhook gateway → durable job queue → email worker → conversation and identity checks → Gemini model + scoped knowledge retrieval → deterministic policy / safety validation → Gmail draft or reply → audit and monitoring.

| Component         | Initial technology / design                                                                                                     |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------|
| Dashboard         | Next.js + TypeScript; internal SSO; reviews, configurations, monitoring.                                                        |
| Backend           | Python FastAPI modular monolith; provider-neutral interfaces.                                                                   |
| Mailbox           | Gmail API with Pub/Sub change notifications; history.list reconciliation and daily watch renewal.                               |
| Async workflow    | Cloud Tasks for delivery and retries; Firestore or PostgreSQL as authoritative job/send state.                                  |
| AI provider       | Gemini behind ModelProvider interface; production option must pass Google Cloud/Vertex AI policy review.                        |
| Knowledge         | Drive authoritative files; controlled export; metadata manifest; Gemini File Search candidate or enterprise-approved retrieval. |
| Database          | Firestore for first Google-native deployment; PostgreSQL if portability and vendor-independent Docker hosting dominate.         |
| Hosting           | Cloud Run for internal first; Docker Compose distribution and customer-hosted deployment path later.                            |
| Secrets / logging | Secret Manager, Cloud Logging, Cloud Monitoring, restricted service accounts.                                                   |

Architecture choice to resolve during discovery: if selling self-hosted software is a near-term requirement, prefer PostgreSQL and an abstracted queue from day one rather than coupling the core workflow to Firestore/Cloud Tasks. Google-specific services remain adapter implementations; on-prem installations need equivalent queue, scheduler and email event handling.

# 6. Knowledge management strategy

8.  Establish company-controlled Google Shared Drive / approved folder; separate drafts, approved-customer-safe, internal-technician and retired documentation.

9.  Catalog file ID, revision, language, brand, product/model, owner, approval status, effective date, visibility and checksum.

10. Extract Docs/Markdown/PDF content, maintain paragraph/section references, normalize file names, and apply document-quality checks.

11. Index approved customer-safe sources in retrieval; filter by brand/model/language and access classification. Do not index all NotebookLM content by default.

12. Use Drive change tokens and scheduled full reconciliation. Reindex versioned documents and atomically retire superseded content.

13. If source approval/index version becomes uncertain, do not auto-send; create review draft or escalate.

14. Run sample retrieval tests after each material knowledge change; retain source/version evidence alongside response records.

# 7. Email processing and auto-send rules

Use Gmail watch + Pub/Sub for change signals, not as the message payload. Workers fetch mail history, inspect message IDs/thread IDs, classify the message and use idempotent job keys. Renew Gmail watches daily and recover from missed notifications using periodic reconciliation.

| Disposition            | Illustrative categories                                                                                                     | Rule                                                                                                                   |
|------------------------|-----------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| Eligible for auto-send | Manual links, supported product specs, basic non-hazardous setup FAQs, request for model/error code.                        | Current approved sources, verified brand/model relevance, no sensitive account info, no contradiction, no human owner. |
| Draft for review       | Ambiguous faults, warranty claims, complaints, uncertain procedures.                                                        | Human agent reviews response, citations and risk tags before send.                                                     |
| Escalate               | Smoke/overheating/electric shock, damaged electrical components, dangerous instructions, customer expressly requests human. | Use fixed approved safety wording when appropriate; route to established support process.                              |

Send safety requirements: review exact recipient and sender; preserve threadId, In-Reply-To and References; exclude auto-responses, mailing lists, spam and own outgoing mail; synchronize human ownership; reserve and reconcile each send operation; rate-limit outgoing messages; kill switch for mailbox/category.

# 8. Security, privacy and governance

- Company-approved Gemini deployment, legal basis and data processing terms must be confirmed; chosen GCP region does not guarantee all model processing remains there.

- Dedicated test and production GCP projects, least-privilege IAM, protected webhook authentication, encrypted secrets and restricted egress.

- Workspace administrator-approved Gmail OAuth; assess scope classification and implications for future public-app OAuth verification/security assessment.

- Data minimization and configurable retention; redact unnecessary personal details from telemetry and evaluation datasets.

- Prompt injection resistance: email bodies, attachments and retrieved documents are treated as untrusted facts, never authorization instructions.

- No credentials in prompts or source control; logs capture metadata, not indiscriminate customer contents.

- Safety policies are enforced by backend rules independent of the LLM; critical-risk advice routes to specialists.

- Contractual, employer/IP and commercialization rights reviewed before using company content, examples, or internal integrations in a sold product.

# 9. Delivery roadmap — illustrative 14–18 weeks

| Phase / duration                   | Key work                                                                                                                              | Exit criterion                                                                                |
|------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| 0\. Discovery (1–2 wk)             | Stakeholder approvals; mailbox type; data classification; 100–300 anonymized tickets; baseline metrics; architecture decision record. | Approved requirements, risk register and non-production access.                               |
| 1\. Foundation (2 wk)              | Repository, environments, IAM, CI/CD, DB, queue, Docker, SSO skeleton, observability.                                                 | Healthy non-production deployment and automated smoke tests.                                  |
| 2\. Knowledge + Gemini (2–3 wk)    | Drive ingest, document registry, retrieval, product tags, evaluation harness, structured agent outputs.                               | Knowledge-only test set meets preliminary correctness/safety gates.                           |
| 3\. Gmail draft pilot (2–3 wk)     | Watch/PubSub, history sync, threading, deduplication, drafting, agent review experience.                                              | Real test mailbox creates safe drafts in existing threads, no duplicate-send in replay tests. |
| 4\. Supervised live pilot (2–3 wk) | Read-only live mailbox processing; drafts; operator scoring; repair gaps; alerts.                                                     | SME-reviewed quality and operations evidence accepted.                                        |
| 5\. Limited auto-send (2 wk)       | Category allowlist, safety gates, kill switch, rollback, controlled cohort and monitoring.                                            | Explicit business/privacy approval and pilot thresholds met.                                  |
| 6\. Stabilize/package (2–3 wk)     | Runbooks, installation wizard, Docker distribution, backup/restore, update tests, licensing/IP assessment.                            | Installation validated in clean test environment; handover signed off.                        |

Schedule is a planning estimate assuming a small dedicated team and timely IT approvals. Actual calendar time depends most on access, knowledge cleanliness, security review and historical email evaluation quality.

# 10. Initial backlog and acceptance criteria

| Priority | Work item                              | Definition of done                                                                                  |
|----------|----------------------------------------|-----------------------------------------------------------------------------------------------------|
| P0       | Approved mailbox and Drive permissions | Nonproduction API calls work using limited, approved identities; secrets managed securely.          |
| P0       | Knowledge registry and retrieval       | Answers cite correct current source and reject obsolete/unauthorized files.                         |
| P0       | Gmail ingestion pipeline               | Missed notifications recover; duplicate events do not duplicate draft/send.                         |
| P0       | Structured answer and policy decision  | Every answer has source references, disposition, safety category and audit record.                  |
| P0       | Manual review / ownership              | Agent can take over or pause a thread; AI respects pause.                                           |
| P0       | Evaluation suite                       | Golden dataset covers brand/model, unsafe cases, German/English and adversarial emails.             |
| P1       | Auto-send controls                     | Allowlist, send limit, kill switch, rollback and post-send monitoring.                              |
| P1       | Deployment package                     | One-command local test deployment with sample env, migrations, health checks and runbook.           |
| P2       | Salesforce/NetSuite read-only adapters | Scoped access to verified customer/order facts, optional and tenant-aware.                          |
| P2       | Commercial edition                     | License mechanism, installation wizard, tenant settings, public OAuth review and support contracts. |

# 11. Quality gates and success metrics

| Metric                     | Proposed gate / measurement                                                                                 |
|----------------------------|-------------------------------------------------------------------------------------------------------------|
| Factual correctness        | ≥95% on the specifically approved low-risk test set, measured by human reviewers.                           |
| Critical safety errors     | 0 observed in defined critical/adversarial evaluation; continuously monitored.                              |
| Duplicate outbound replies | 0 in deterministic replay, retry and failure-injection tests.                                               |
| Grounding                  | 100% of substantive technical replies link to traceable approved source excerpts internally.                |
| Human override             | All test takeover/stop scenarios prevent further automatic replies.                                         |
| Deflection / resolution    | Track customer-confirmed or follow-up-inferred resolution separately from emails sent.                      |
| Operational reliability    | Set SLOs after mailbox volume baseline; alert on sync lag, webhook failures, queue backlog and error rate.  |
| Business impact            | Minutes saved per eligible email, human correction rate, repeat contacts, CSAT and cost per resolved issue. |

No single accuracy score makes the system safe. In addition to aggregate metrics, require category-specific failures, multilingual tests, model/version regression, evaluation of uncertain cases and approval by customer-service and safety stakeholders.

# 12. Resourcing and budget assumptions

| Workstream               | Indicative involvement                       |
|--------------------------|----------------------------------------------|
| Product/PM               | 0.3–0.5 FTE across delivery                  |
| Backend / AI engineering | 1–2 FTE across delivery                      |
| Cloud / DevOps           | 0.3–0.5 FTE, heavier at setup/go-live        |
| Support SMEs + QA        | 0.3–0.7 FTE for evaluation and policy review |
| Security/legal           | Part-time approval at defined gates          |

Cost buckets to estimate with real volume: labor; Gemini model tokens; retrieval indexing; Cloud Run/queue/database/logging; Gmail/Drive API operating overhead; security review; maintenance/support; backups and evaluation review. Do not commit to a fixed euro budget before measuring daily email volume, typical thread length, KB document size and privacy requirements.

Planning scenarios (illustrative, not vendor quotes): prototype with mocked data and drafts; controlled production with selected auto-send categories; enterprise packaging for third-party customers. Ask engineering to produce low/base/high monthly cost scenarios and cost per resolved email at the end of discovery.

# 13. Risk register

| Risk                                       | Impact      | Mitigation / owner                                                                           |
|--------------------------------------------|-------------|----------------------------------------------------------------------------------------------|
| Wrong electrical safety guidance           | Critical    | Hardcoded escalation triggers, approved technical sources, safety SME tests; Support/Safety. |
| Outdated or cross-product knowledge        | High        | Versioned manifest, model filters, reindex and source expiry; Knowledge owner.               |
| Unapproved data transfer to model          | High        | Vendor/privacy review, data minimization, access audit; Security/Legal.                      |
| Duplicate, looping, or misaddressed emails | High        | Idempotency, thread checking, recipient validation, send reconciliation; Engineering.        |
| Google OAuth / API access delays           | Medium–high | Start approvals in phase 0; test mailbox; Workspace admin owner.                             |
| Overestimated automation savings           | Medium      | Representative historical dataset, shadow pilot, verified resolution metrics; PM.            |
| Future self-hosted portability debt        | Medium      | Provider interfaces, Docker, PostgreSQL path, deployment documentation; Engineering.         |
| Employer IP / commercialization conflict   | High        | Written ownership/licensing approval and clean-room demo assets; Sponsor/Legal.              |

# 14. Commercialization pathway (after internal value proven)

15. Separate general-purpose core, email/model/knowledge adapters, and customer-specific configuration/documentation in code and deployment boundaries.

16. Create white-label branding, installation wizard, environment validation, backup/restore, encrypted credential setup and health diagnostics.

17. Package Docker containers and release versioned upgrades with compatibility and migration tests.

18. Define supported connector matrix: Gmail + Gemini + Drive first; Microsoft 365 and alternative model/knowledge adapters later.

19. Provide sample data, evaluation harness, admin manual, service-level support model, telemetry policy and paid maintenance arrangements.

20. Review licensing, third-party dependencies, Google OAuth external-app verification requirements and legal permission to commercialize.

21. Pilot on a second independent test installation to validate repeatability before selling licenses.

# 15. First 10 working-day action plan

| Day | Owner / action                                                                          | Output                                        |
|-----|-----------------------------------------------------------------------------------------|-----------------------------------------------|
| 1   | PM + Sponsor: agree use cases, exclusions, target mailbox and success metrics.          | Signed scope and owner list.                  |
| 2   | IT: confirm Gmail mailbox type and administrator approval path.                         | Gmail access decision.                        |
| 3   | Knowledge owner: identify approved Shared Drive source folders and ownership.           | KB inventory, approval scheme.                |
| 4   | Security: Gemini API/Vertex route, DPA, regions, retention and PII decisions.           | Security/privacy prerequisites.               |
| 5   | Support SMEs: select anonymized cases by issue, model and language.                     | Evaluation dataset outline.                   |
| 6   | Architecture lead: decide Firestore/GCP-first vs PostgreSQL/portable core.              | Architecture decision record.                 |
| 7   | DevOps: prepare dev GCP project, roles, CI, secret conventions.                         | Non-prod environment checklist.               |
| 8   | Engineering: define canonical email, conversation, document and agent decision schemas. | Interface specifications.                     |
| 9   | QA: author measurable automatic-send and escalation rules.                              | Acceptance test matrix.                       |
| 10  | PM: baseline email load, validate staffing/effort, schedule milestone reviews.          | Approved implementation backlog and timeline. |

# 16. Outstanding decisions for the project manager

- Who owns the support mailbox and is it a Gmail user inbox, group, or third-party helpdesk route?

- Which Google Gemini/Vertex model endpoint and data-processing terms are approved for customer messages?

- Which Drive knowledge files are explicitly customer-safe and who approves updates?

- What existing customer support ticket route will receive escalations?

- Is self-hosted commercial sale permitted, and who will own code and derivative intellectual property?

- What automation percentage, quality floor and budget justify production expansion?

- Which language/product model coverage is mandatory at first launch?

# 17. References and assumptions

Primary technical references (review again during implementation):

https://developers.google.com/workspace/gmail/api/guides/push

https://developers.google.com/workspace/gmail/api/auth/scopes

https://ai.google.dev/gemini-api/docs/file-search

https://knowledge.workspace.google.com/admin/apps/control-which-third-party-and-internal-apps-access-google-workspace-data

https://support.wallbox.com/en/knowledge-base/

https://www.ablmobility.de/de/service/support/

Assumptions: Google Workspace/Gmail is used for email; approved knowledge files are in Google Drive and linked into NotebookLM; first release is internal-only and email-only; the existing support chatbot/ticket process remains in place; Salesforce/NetSuite are later optional read-only connectors. Estimates and targets are proposals pending discovery.
