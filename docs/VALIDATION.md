# Implementation validation — 30 October 2026

Verified in the managed development environment against synthetic fixtures only.

| Check | Result |
| --- | --- |
| `cd backend && uv run ruff check .` and helper-script lint | Passed |
| `cd backend && uv run pytest -q` | **63 passed**; one upstream Starlette TestClient/httpx deprecation warning |
| `cd dashboard && npm run build` | Passed, Next.js production build |
| `cd dashboard && npm run typecheck` | Passed |
| Both Docker image builds | Passed with TLS verification and the managed proxy CA preserved |
| Compose/PostgreSQL startup and repeated rebuild/start | Passed; database/API/dashboard healthy; schema and seed completed successfully |
| `python3 scripts/smoke.py` | Passed: health/auth, five durable worker drafts, safety escalation, citations, dashboard session/proxy and cross-origin rejection |
| `docker compose exec -T api python - < scripts/check_postgres.py` | Passed: eight concurrent ingests → one message/job; eight concurrent sends → one demo adapter call |
| `CHROMIUM_PATH=/usr/bin/chromium npm --prefix dashboard run test:e2e` | **2 passed**: actual browser review/approval, evidence, takeover/resume, risk blocking, keyboard focus wrap, operations and mobile overflow |
| `bash -n scripts/dev.sh` | Passed syntax check; Docker is the fully exercised startup path |

Desktop and mobile screenshots in `docs/assets/` are captures of the synthetic workspace, not designs or mockups.

No live Gmail, Drive, Gemini, corporate SSO, Cloud Run deployment, backup restore, production safety/correctness benchmark, or GitHub-hosted CI run is claimed by these local results. Google adapter tests use controlled responses. Review the delivery map before connecting company data or enabling any automated replies.

## Cloudflare Workers target

- OpenNext 1.20.14 / Wrangler 4.156.0 bundle build: passed.
- Existing Chromium review/approval/ownership and mobile tests against the actual local Workers runtime (`DASHBOARD_URL=http://localhost:8787`): **2 passed**.
- Local Workers login and authenticated backend overview/inbox proxy: verified against the running synthetic backend. Local operator credential was checked absent from built JavaScript; `.dev.vars`, `.wrangler`, and `.open-next` are ignored by Git.
- Deployment preflight correctly rejects the unset backend URL.
- Live publication: **blocked**. Wrangler reports no authenticated Cloudflare account, and the user confirmed no hosted backend exists. No workers.dev URL or live deployment is claimed.

## Render single-service package

- `Dockerfile.render` built successfully with the managed proxy CA and TLS verification retained.
- A separate synthetic PostgreSQL database was initialized and seeded by the combined container.
- Functional checks passed for database-backed `/api/health`, Secure/HttpOnly login cookies, the dashboard API proxy, unauthenticated API rejection, a new job processed by the bundled worker, citation evidence, and default send protection.
- The Blueprint explicitly requests free web/database plans. Provider eligibility, current free-plan availability/expiry, and Blueprint acceptance remain unverified until account provisioning.
- No Render deployment actions or credentials were exposed to this session, including after the Render app was tagged. No public deployment or live URL is claimed.

## Business onboarding update

- Backend suite: **81 passed**, including encrypted storage/no secret echoes, preserved blank secrets, disconnect, expired/failed verification, hot-loaded draft-only activation, provider-context isolation, arbitrary business brands/general policies, source retirement, and additive upgrades preserving existing records.
- Updated Render-ready image built successfully. A separate PostgreSQL test database was used; the existing demo and live Render database were not modified by these checks.
- Browser suite against that deployable image: **3 passed**. Existing review/takeover/safety behavior, mobile layout, company profile/knowledge entry, masked secret persistence across reload, readiness blocking, and demo/live inbox separation were verified.
- TypeScript type check and Python/helper lint passed. Live Google authorization and model behavior still require administrator-provided credentials and approval; read-only provider verification is available in Business setup.
- PostgreSQL concurrency was rechecked with the provider-origin table: eight concurrent ingests still create one message/job, and eight send attempts still make one demo adapter call. The helper now refuses configured business databases.

## Guided integration release

- Backend suite: **107 passed**. Additional cases cover PKCE/state/browser binding, one-time/expired OAuth sessions, token/error redaction, trusted provider origins, fixed/escaped read-only customer queries, rotating token persistence, concurrent credential edits, Drive folder scope, preview/revision approval and revocation, sync-versus-retirement races, and bounded exact-source excerpts for larger documents.
- Production Next.js build and type checking passed. The combined deployment image was built; final backend source was layered into the same validated runtime/dependencies for the final container check.
- Browser suite against the PostgreSQL-backed deployment container: **4 passed**. This includes guided Google account connection with PKCE, an HttpOnly browser binding, rejected forged callback, existing review/safety/ownership behavior, mobile layout, and persisted company/secret setup.
- The final startup script was checked with an explicit dashboard origin differing from Render's supplied origin; the same four browser tests passed with the explicit origin taking precedence.
- The external provider consent page is mocked in the browser test; provider REST/token contracts are mocked in backend tests. No live Google, Salesforce or NetSuite account was connected, and no real customer messages or CRM records were processed. Administrators must register/approve OAuth clients and verify their actual account permissions in the deployed app.

## Personal-account testing preparation

- Re-ran the unchanged integration release: **107 backend tests passed**, **4 browser tests passed**, and the combined container's database-backed health check passed.
- PostgreSQL checks in the combined deployment container passed: eight concurrent ingests produced one message/job and eight send attempts produced one synthetic adapter call. A disposable database was used, then removed; the existing application database was preserved.
- Added [a two-account manual test guide](PERSONAL_TEST.md), English/German synthetic source files, 30 user-function checks and optional CRM sandbox checks. These are instructions and pending acceptance checks, not fabricated live results.
- Real Google sign-in, Gemini generation, Gmail delivery, Salesforce and NetSuite remain untested in the user's accounts. This environment's outbound destination policy does not permit the public Render/Google service hosts, and no live provider account credentials are configured here. These checks must be completed through the deployed app with the account holder's consent.

## Personal setup and provider buttons

- Backend suite: **115 passed**. New cases cover personal mailbox discovery, encrypted credentials/host-secret redaction, explicit consent and paused activation, concurrent profile changes, immutable live mailbox identity, protection of live business installations, authenticated Drive folder selection, and host-configured Salesforce/NetSuite authorization.
- Production Next.js build, TypeScript checking, Python lint and patch whitespace checks passed. The new production dashboard and backend were packaged into the previously validated combined deployment runtime; its PostgreSQL-backed health check passed.
- Browser suite against the final disposable deployment: **8 passed**. New checks cover personal setup as the entry point, truthful missing-host settings, knowledge folder selection/approval, Gemini verification and explicit activation, and Salesforce/NetSuite button-to-provider PKCE flows with browser binding and forged callback rejection. Business setup/review/mobile regressions also passed.
- The personal folder/key/activation browser exercise mocks backend responses to test UI behavior. Provider consent pages are intercepted, and provider token/REST contracts remain mocked in backend tests. No live account was connected or real email sent; registered host OAuth clients remain required. Test containers/databases are disposable and do not modify the existing application database.

## Separate company and personal test environments

- Backend suite: **120 passed**. Additional cases check separate persistent test storage, separate encryption context, independent jobs/messages, rejection of personal-profile conversion through the company API, and distinct OAuth callback paths. Production build, TypeScript, lint, shell syntax and Compose/managed-CA overlay validation passed.
- Browser suite against the combined deployment: **10 passed**. Company setup is the default; personal testing is a separate switch. Knowledge with the same ID remained separate across environment switches and concurrent browser tabs. Workspace switching requires operator authentication, valid origin and a supported target. Existing Google/Salesforce/NetSuite PKCE, review, mobile and business setup checks also passed.
- A real PostgreSQL disposable database used public company tables and the `supportflow_personal_test` schema. A test worker processed a message sharing a company message ID, test credentials used a distinct encryption key, and a snapshot of all company tables was unchanged by test operations. Both API health checks and the original local application health check passed.
- The disposable dual-API/dual-worker image used the new production dashboard, backend and startup script in the previously validated runtime. The initial attempt hit execution-workspace disk capacity before test database creation; unused build artifacts/cache were removed and the test was completed successfully. No company database/volume was deleted.
- Provider consent/token responses and the personal key/knowledge activation browser exercise still use controlled fixtures. These results do not establish a live Google grant, real model quality or email delivery. The two environments share hosting, operator access and by default a database server; this is storage/workflow isolation, not separate customer authorization or independent hosting failure domains.
