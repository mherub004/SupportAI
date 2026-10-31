# Single-service demo hosting

The Render Blueprint bundles Next.js, FastAPI and the Python worker into one Docker web service, with a separate persistent PostgreSQL database. It avoids a separate public backend URL.

## Launch

Open [Deploy on Render](https://render.com/deploy?repo=https://github.com/mherub004/SupportAI), sign in or create an account, and grant access to this GitHub repository. Review `render.yaml`: both resources explicitly request the **free** plan. Verify current free-tier availability, eligibility, quotas and database expiry in the provider's UI. If a free plan is unavailable, stop rather than selecting a paid upgrade. No charge or paid plan is authorized by this setup.

Render builds `Dockerfile.render` and supplies the PostgreSQL connection and a randomly generated `OPERATOR_TOKEN`. Once deployment succeeds, use the actual HTTPS URL Render supplies. Retrieve the operator token securely from the service's Environment settings to sign in; do not paste it into chat, Git or public logs. No credentials are embedded in the image.

The deployment starts in synthetic **demo** mode with automatic sending disabled. `/api/health` verifies API/database readiness. The API is loopback-only inside the container; authenticated dashboard requests proxy to it. The dashboard, company API/worker and personal-test API/worker restart together if any exits. Test data uses its own PostgreSQL schema; no second database plan is required. Keep this demo to one instance.

## Free-tier limitations

Free web services may sleep. Queue processing and scheduled Gmail/Drive work stop during sleep and resume only when the service wakes. Database quotas/expiry may interrupt service or remove data according to the provider's current policy. Maintain backups and check those terms before use. The app requires PostgreSQL and does not silently use ephemeral SQLite.

This is a demonstration, not always-on production email automation. Do not connect customer mailboxes or enable automated replies on sleeping infrastructure. Production requires the original plan's approvals, always-on hosting, backups, monitoring and SSO.

## What can be verified without an account

The combined image can be built locally and tested against PostgreSQL, including schema initialization, synthetic seed, health, login, backend proxy and actual queue processing. Local tests cannot verify Render account eligibility, Blueprint acceptance or successful public deployment. Signing in and approving the provider's resource creation must happen in your own account.

## Configure your company

After deployment, sign in to **Company workspace → Business setup**. Use the separate [Personal test environment](PERSONAL_QUICKSTART.md) beside it for your own Gmail trial. No business/provider credentials are required to launch. Set the registered Google OAuth client ID/secret as backend environment variables once to enable personal Google sign-in; optional Salesforce/NetSuite host credentials enable their sign-in buttons. See [onboarding](BUSINESS_SETUP.md). Existing deployments receive additive configuration tables automatically at startup; customer/source records are preserved. Keep OPERATOR_TOKEN stable because it is the default connector-encryption key source. Free service sleep still prevents reliable scheduled processing.
