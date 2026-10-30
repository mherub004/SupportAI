# Deploy the dashboard to Cloudflare Workers

The dashboard supports Cloudflare Workers through the OpenNext adapter. **The FastAPI API, durable Python worker, and PostgreSQL remain separate services.** This deployment does not move them into the JavaScript Worker or make a localhost API accessible from Cloudflare.

## Prerequisites

- A Cloudflare account with Workers deployment permission and a workers.dev subdomain (or configured custom domain).
- An approved HTTPS host for the existing API/worker/database stack. Keep API bearer authentication enabled, restrict ingress where practical, and enable HTTPS. Do not expose a development machine with customer data.
- The backend's existing `OPERATOR_TOKEN`, supplied securely as a Worker secret. Never put it in `vars`, Git, command-line arguments or chat.
- Node.js 22+ and the frozen npm dependencies in `dashboard/`.

## Deployment

From `dashboard/`:

1. Run `npm ci` and `npx wrangler whoami`. If unauthenticated, run `npx wrangler login` on your own machine and complete Cloudflare authorization. CI can use securely configured `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`; never commit either.
2. Edit `vars.API_URL` in `wrangler.jsonc` to the actual backend HTTPS **origin**, with no credentials, query string or path. The deployment preflight rejects an empty/placeholder/local URL. The tracked empty value is intentional: a dashboard without a reachable API is not a working hosted application.
3. Optionally change `name` and the matching `WORKER_SELF_REFERENCE.service` together. Default Worker name: `supportflow-ai`.
4. Run `npx wrangler secret put OPERATOR_TOKEN` and enter the existing backend token through the CLI's secure prompt. Use the same token on the Python backend; do not generate an unrelated dashboard-only token.
5. Run `npm run worker:deploy`. This checks the backend setting, builds Next.js/OpenNext, and deploys the Worker/assets. Use the actual URL Wrangler returns; no hosted URL is assumed here.
6. Keep `COOKIE_SECURE=true`. For a fixed domain, add `DASHBOARD_ORIGIN` in Wrangler vars with that exact HTTPS origin and redeploy. If omitted, the session route validates against the incoming request origin.
7. Validate the deployed login and authenticated inbox/knowledge/operations calls, reject invalid tokens and cross-origin mutations, and confirm real draft evidence is available. Do not enable automatic sending as part of hosting setup.

`nodejs_compat` with the configured compatibility date supplies Workers environment bindings to Node's `process.env`, which the existing server routes use. The dashboard has no ISR pages and uses no R2 cache uploader. Secrets are accessed only by server-side routes, not bundled into client JavaScript.

## Local Workers preview

Build with `npm run worker:build`. Copy `.dev.vars.example` to ignored `.dev.vars`, replace its operator token with the existing local backend token, and keep the local Python/Compose stack running. Run `npx wrangler dev --local --port 8787`. The local preview uses an HTTP backend and explicitly non-Secure cookies; these overrides belong only in `.dev.vars`, never production vars.

A successful bundle or local preview is not a live deployment. Cloudflare account authorization and a reachable hosted backend are required before publication can complete.
