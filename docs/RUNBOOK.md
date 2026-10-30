# Pilot operating runbook

## Routine start and readiness

Use existing checkouts in isolated cloud tasks; do not create a worktree unless explicitly requested. From the checkout root, create local configuration once with `python3 scripts/configure.py`, then run `docker compose --profile demo up --build -d --wait` for the demo (omit the profile in Google mode). In the managed cloud use `-f compose.yaml -f compose.cloud.yaml` for session CA trust. Do not rely on processes surviving environment snapshots.

Run `python3 scripts/smoke.py` only in demo mode. It checks DB-backed API health, auth rejection, five worker-created drafts, safety escalation, evidence citations, dashboard login/proxy and cross-origin login rejection. A healthy port alone is not readiness. The smoke script expects unsent seeded demo drafts; run send experiments with separate message IDs. Browser tests use the synthetic demo too.

## Review and ownership

Inspect exact recipient, thread, response and source revisions in the dashboard. Enter a meaningful correction/review reason; approval updates the exact Gmail draft. Sending additionally requires an off kill switch, current evidence, no risk tags, no prior reservation and an unpaused thread.

Use **Take over** to pause a thread before working it manually. Human Gmail replies also conservatively pause sends for that thread. This pilot considers any non-SupportFlow SENT message in the thread human-owned, including an older human reply. Resume the application only after reviewing the real mailbox; the Gmail human-reply check can still block it. There is no override bypass in the app.

Escalated cases are marked in the review queue and have generic human-review drafts; they are **not** automatically forwarded or turned into tickets. Operators route them through the existing support process. Configure that process and its accountable owner before a live pilot. Sending risk-tagged cases directly from Gmail is a human action outside this application's automation path.

## Failures and uncertain operations

- Jobs retry with exponential backoff, up to five attempts. The Operations view exposes job state/error type. Provider failures should be diagnosed by credential/permission/quota state, not by dumping tokens or customer request bodies.
- `draft_creating`, `draft_updating` or `draft_uncertain` can mean Gmail accepted a request before the client failed. Do not delete the message row or blindly requeue draft creation. Use the reconciliation endpoint/CLI or inspect Gmail manually.
- `reserved`, `send_uncertain` or an uncertain Send row means the outcome is ambiguous. Reconcile by deterministic RFC Message-ID. If Gmail confirms sent, state becomes sent; if nothing is found, retry remains blocked because Gmail search absence may be delayed or incomplete.

```sh
docker compose exec api python -m app.cli reconcile --message-id THE_GMAIL_MESSAGE_ID
```

The authenticated API has `POST /api/messages/{id}/reconcile` as well. Reconciliation never sends a second copy. After a draft update uncertainty, reconciliation restores a draft for a fresh review, not automatic approval.

If a process crashed with an old `draft_updating` state, inspect Gmail manually; this first version does not auto-reset in-flight updates. Never modify SQL state merely to make a send retry pass.

## Knowledge freshness

A Drive refresh marks the index uncertain before fetching. Failed exports, changing source revisions or invalid metadata leave sends blocked. Correct the prerequisite, then queue `/api/sync/drive` or let the hourly schedule retry. No partial inventory is activated. Removed/unapproved files are retired atomically on the next successful sync.

A knowledge owner must set expiry dates where needed. This version does not alert on an aging successful sync; monitor worker liveness and last sync audit time. Disable sending during source-governance incidents or worker outages.

## Retention

Choose the lawful retention period with privacy stakeholders. Default is 30 days. Schedule the following command daily using your approved scheduler (not automatically installed by Compose):

```sh
docker compose exec -T api python -m app.cli purge
```

This removes old message bodies, headers, recipients, response text and citation excerpts, plus old audits/completed jobs. Minimal message/send identity tombstones remain for deduplication and ambiguous-send protection. It does not erase Gmail/Drive, backups, provider logs or model-side retention. Establish separate policies for those systems and for eventual tombstone deletion. Purged messages cannot be sent by this app.

## Backup and restore

Backups contain customer/source content and must be encrypted and access-controlled. Use a PostgreSQL-compatible backup tool, e.g.:

```sh
mkdir -p backups
chmod 700 backups
docker compose exec -T db pg_dump -U supportflow -d supportflow -Fc > backups/supportflow.dump
chmod 600 backups/supportflow.dump
```

Store backups outside source control (add your backup directory to local ignore rules). Validate restore into a **separate** isolated database with network sending disabled and new local credentials; never restore over live data without a planned maintenance/rollback procedure. Run schema/health checks, verify message/job/send counts, and confirm uncertain sends remain blocked before resuming. Do not send from both the restored and original installation.

The initial release creates schema v0.1 only; it does not run automatic upgrade migrations. Snapshot/backup before a future schema change and implement/test the corresponding migration first.

## Monitoring and deployment

Track worker liveness, failed/pending jobs, Gmail history lag, watch expiration, knowledge refresh age, uncertain sends, rate-limit blocks and operator corrections. `/api/overview`, `/api/jobs` and audit metadata are initial diagnostic sources. Export them through an approved monitoring system; paging/SLOs, business analytics, CSAT and confirmed-resolution metrics are not automatically supplied.

For containment, enable the mailbox kill switch and stop the worker. Already in-flight requests may still complete; reconcile them before restarting. Keep secrets and database state through redeploys. Restarting/replaying must never clear Send reservations.
