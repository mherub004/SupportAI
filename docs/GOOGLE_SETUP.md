# Nonproduction Google connector setup

No live calls are required for the synthetic demo. Live connector behavior has automated contract tests, but must be validated against your own approved test mailbox and knowledge folder before any live pilot.

## Required organizational inputs

Use a dedicated **Gmail user mailbox**, not a Google Group. Obtain Workspace administrator consent and the least-privilege access needed by the chosen authentication route. Confirm the model's data-processing terms, customer-content policy, region behavior, retention, and escalation ownership. No model endpoint is approved merely because this code supports it.

Store raw OAuth refresh credentials securely in your deployment secret manager. Proxy-injected secret placeholders can be used only for supported HTTPS destinations; a refresh token submitted in a form body must be a real process-readable credential supplied securely, not a proxy placeholder. Never paste values into issues, chat, source files, screenshots or logs.

## Authentication

The Gmail/Drive adapter tries these routes in order:

1. `GOOGLE_REFRESH_TOKEN` with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (server-side OAuth refresh).
2. `GMAIL_ACCESS_TOKEN` for a short-lived test session (must authorize both Gmail and Drive if used for both).
3. Google Application Default Credentials with Gmail/Drive scopes. Normal GCP service-account ADC alone cannot access a Workspace user mailbox; domain-wide delegation/impersonated user credentials must be explicitly configured by your administrator, or use the refresh route.

Requested adapter scopes are `https://www.googleapis.com/auth/gmail.modify` and `https://www.googleapis.com/auth/drive.readonly`. Gmail modify is a restricted scope and allows reading, drafts, sending and label changes. OAuth verification and scope minimization need a deployment-specific assessment. The registry reads only the selected folder but Drive readonly scope itself grants broader access; restrict the underlying identity to approved sources. Do not expose this pilot as a public OAuth application.

Set `MAILBOX` exactly to the authenticated user's primary Gmail address. The adapter checks Gmail profile identity before draft/send and mailbox synchronization. Configure `CONNECTOR_MODE=google`; do **not** start the demo profile against real data.

## Gemini

Set `GEMINI_API_KEY` and the approved `GEMINI_MODEL` identifier (default candidate: `gemini-2.5-flash`; availability must be confirmed for your account). This adapter calls `generativelanguage.googleapis.com` with a header credential and structured JSON. It uses no training, File Search corpus or NotebookLM content. Vertex AI is not silently substituted: implement/review its provider separately if required by your policy.

The entire bounded plain-text inbound email is sent to the configured model; there is no full PII anonymizer. Credentials and unrelated headers/attachments are not sent. Production content handling requires your privacy approval and any further redaction rules.

## Approved Drive folder

Set `DRIVE_FOLDER_ID` to the approved folder/Shared Drive folder. Only direct children are ingested. Supported MIME types: Google Docs export to plain text; UTF-8 Markdown/plain text; text-extractable PDF up to 10MB. PDF evidence includes page markers. Scanned PDFs need OCR outside this pilot.

An authorized knowledge owner must set these **Drive `appProperties`** through the same OAuth application that reads them (appProperties are application-private):

| Property | Required value / example |
| --- | --- |
| `supportflow_approved` | `true` only after human approval |
| `visibility` | `customer_safe` |
| `brand` | `ABL` or `Wallbox` |
| `model` | Exact, canonical product model name |
| `language` | `de` or `en` |
| `owner` | Accountable knowledge owner |
| `effective_at` | ISO 8601 timestamp, e.g. `2026-10-30T00:00:00Z` |
| `expires_at` | Optional ISO timestamp; required by policy if the source can expire |
| `customer_url` | Optional approved HTTPS customer-facing manual URL; mandatory for automatic manual-link replies |

Missing/invalid metadata cannot create approved evidence. Do not set these flags for internal technician procedures. Source approval, ownership and public customer links must be verified by the knowledge owner. The code does not approve company materials or make files public.

Manual local records can be imported through authenticated `PUT /api/knowledge` using the OpenAPI schema, with `id` not prefixed `drive:`. Include all classification, approval, dates and content fields; defaults do not grant approval.

## Gmail watch and Pub/Sub

1. Enable Gmail, Drive and Pub/Sub APIs in the approved test project.
2. Create a Pub/Sub topic; grant `gmail-api-push@system.gserviceaccount.com` publisher access as described in Google's Gmail push guide. The topic project must satisfy Gmail watch project constraints.
3. Set `GMAIL_TOPIC=projects/YOUR_PROJECT/topics/YOUR_TOPIC`.
4. Configure an authenticated Pub/Sub push subscription to your HTTPS `/webhooks/gmail` endpoint. Use a dedicated push service account; grant the Pub/Sub service agent permission to mint its identity token.
5. Set `GOOGLE_PUBSUB_AUDIENCE` to the exact configured token audience, and `GOOGLE_PUBSUB_SERVICE_ACCOUNT` to that service account's email. JWT signature, issuer, expiry, audience, verified email and mailbox are checked before queueing.
6. The worker renews watch once daily and reconciles history every minute even without notifications. The Pub/Sub payload is only a signal; message bodies come from Gmail API history/message fetches.

Initial/expired-cursor reconciliation processes **the last seven days of inbox mail**, not the whole mailbox. Choose a dedicated low-volume test mailbox and do not import real historical mail accidentally. Plan an explicit historical migration and paging/volume controls before expanding this window.

## Required outbound destinations

Keep existing allowlists. Add only the destinations your deployment needs:

- `www.googleapis.com` — Gmail/Drive REST and Google signing certificates
- `oauth2.googleapis.com` — OAuth refresh
- `generativelanguage.googleapis.com` — Gemini Developer API
- `accounts.google.com` — account/OpenID endpoints if your chosen auth route needs them
- Your approved identity/SSO, secret manager and customer-source destinations, if applicable

Package registries are needed only for building/installing. Preserve configured proxy and CA trust; never disable TLS verification. The `compose.cloud.yaml` overlay mounts the managed public CA bundle for builds/runtime without baking session credentials into images.

## Test before live use

Keep auto-send disabled and kill switch enabled. Trigger authenticated `/api/sync/drive`, inspect the registry, then `/api/sync/gmail` and `/api/sync/watch` as appropriate. Confirm real test drafts remain in the original Gmail thread, contain the expected recipient/headers and only approved evidence. Exercise duplicate notifications, missed-history recovery, expired OAuth credentials, human replies, source revocation and uncertain-send reconciliation using test messages.

Automatic sending additionally requires both `AUTO_SEND_ENABLED=true` and `PRODUCTION_APPROVED=true`, a disabled kill switch, a current source with customer URL, no risk/ownership flags, and the category allowlist. These environment flags **record a deployment choice; they are not evidence that business/privacy approval happened**. Never enable them until the plan's real evaluation and go-live gates have been met.
