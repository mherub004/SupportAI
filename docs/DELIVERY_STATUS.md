# Delivery status against the proposal

The original plan is preserved verbatim in [PROJECT_PLAN.md](PROJECT_PLAN.md). Its approval requests are project requirements, not evidence that stakeholders granted approvals. This initial repository delivers a runnable software pilot and the technical basis for later phases; it does not claim the entire organizational rollout has happened.

| Plan area | Implemented in this version | Remaining acceptance work |
| --- | --- | --- |
| Phase 0 discovery | Scope/exclusions documented; portable-core architecture decision | Actual sponsor/IT/privacy approvals, mailbox ownership, volumes, budget, IP decision |
| Foundation | FastAPI, Next.js, PostgreSQL, SQL queue, local/Docker startup, CI, health/auth checks | Enterprise SSO/RBAC, immutable audit, secret manager/IAM, GCP deployment, versioned upgrade migrations |
| Knowledge | Approved registry, scope/date/revision checks, Drive export/full reconciliation, PDF page markers, citation evidence | Knowledge-owner approvals on real sources; Drive change-token ingest, large-file chunking/OCR, enterprise search/index eval |
| Gemini | Structured-output REST provider and deterministic demo model; bounded evidence context | Real model endpoint/API validation, vendor privacy approval, Vertex adapter if required, representative SME-reviewed evaluation |
| Gmail draft pilot | OAuth refresh/ADC adapters, history/push/watch/reconcile, drafts/threading, exclusions, dedup, ownership, review | Administrator-approved test account and end-to-end real Google validation; public OAuth consent/verification if needed |
| Escalation | Deterministic safety/human-request disposition, review queue and generic draft | Configure accountable existing ticket/support handoff; company-approved safety wording; no automatic ticket connector yet |
| Supervised pilot | Exact review/approval workflow, correction reasons, source evidence, job/audit inspection | Real supervised cohort, human quality scoring, repair/regression cycle, resolution/CSAT and cost measurement |
| Auto-send | Off by default; manual-link template only; category/gate/source/recipient/ownership/rate/kill-switch checks; reserved/uncertain-send protection | Explicit real go-live authorization, category-specific multilingual/adversarial evaluation, Gmail race-window handoff policy; specs/setup/clarification stay review-only |
| Stabilization/package | Compose, frozen locks, synthetic seed, smoke/browser/backend tests, retention/backup/recovery instructions | Clean independent installation/customer pilot, tested backup restore, release upgrade migrations, installation wizard, monitoring/alerts |
| Optional connectors / commercial | Provider interfaces and portable state | Salesforce/NetSuite/M365 adapters, tenant isolation, licensing/IP and public OAuth assessment, paid support arrangements |

## Acceptance evidence

Use actual test output recorded in the implementation handover. The suite includes deterministic risk cases, bilingual synthetic fixtures, product/language/source isolation, injection attempts, replay, timeouts/crash reservations, exact Gmail headers, human takeover, source invalidation, authenticated webhook deduplication, and operator API review/send flows. Mocked Google contracts prove application behavior under those responses, not actual Google authorization or interoperability in your tenant.

The proposed ≥95% factual correctness, zero observed critical safety errors on the **approved real evaluation set**, verified-resolution rate and stakeholder sign-off cannot be established from synthetic tests. A versioned anonymized evaluation corpus and named human reviewers must supply that evidence. Use this review template:

| Case ID | Brand/model/language | Expected disposition | Actual | Current source/version | Reviewer | Correctness | Safety | Correction/reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| YOUR_APPROVED_CASE | | | | | | | | |

Assess each risk/language/category separately. Zero observed errors is bounded evidence, not proof of universal safety. Do not enable automated customer replies solely because tests pass.

## Business setup extension

The deployable app now opens Business setup and supports persistent company/profile policies, encrypted Google/Gemini configuration, read-only access verification, approved manual knowledge entry/retirement, readiness checks, and draft-only activation without redeployment. Product families are configurable; company-wide `general` policies are supported. API/worker settings reload from the database, while provider origins keep demo messages out of live Gmail operations.

The deployment model is still **one installation/database per company**, not public multi-tenant signup. Google OAuth consent/administrator provisioning, individual staff SSO/RBAC, unsupported connector implementations, regulated-industry policy approval, and always-on production operations remain separate requirements. There is no claim of automatic compatibility with every service or business process.
