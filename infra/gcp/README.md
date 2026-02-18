# GCP Deployment Bootstrap

This folder defines the target infrastructure shape for production deployment.

## Planned Services
- Cloud Run: `hiring-agent-api`
- Cloud SQL (PostgreSQL): `hiring-agent-db`
- Pub/Sub topics:
- `screening-jobs`
- `reminder-events`
- Secret Manager:
- `whatsapp-api-token`
- `telephony-api-token`

## Suggested rollout order
1. Provision Cloud SQL and private service networking.
2. Deploy API container to Cloud Run.
3. Attach service account and required secrets.
4. Configure Pub/Sub topics and push subscriptions.
5. Point Netlify frontend API base to Cloud Run URL.
6. Apply alerting policy in `infra/gcp/monitoring/alert-policy.yaml`.

## Environment variables
- `APP_ENV=production`
- `DATABASE_URL=<cloud-sql-connection-string>`
- `WHATSAPP_WEBHOOK_SECRET=<secret>`
- `TELEPHONY_WEBHOOK_SECRET=<secret>`
- `AUTH_ENABLED=true`
- `JWT_SECRET=<secret>`

## Deploy command
- `bash infra/gcp/cloudrun/deploy.sh`
