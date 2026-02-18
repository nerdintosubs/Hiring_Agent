# Pilot Go-Live Runbook

## Preconditions
- Cloud SQL/PostgreSQL database provisioned.
- Secrets created: `DATABASE_URL`, `JWT_SECRET`, webhook secrets.
- `AUTH_ENABLED=true` for production.
- Cloud Run service account has access to Secret Manager.

## Deploy Steps
1. Set `PROJECT_ID` and optional `REGION`.
2. Run `bash infra/gcp/cloudrun/deploy.sh`.
3. Verify deployment URL responds on `/health` and `/health/ready`.
4. Enable alert policy from `infra/gcp/monitoring/alert-policy.yaml`.

## Smoke Tests
1. `GET /health` returns `200`.
2. `GET /metrics` exposes counters.
3. `POST /campaigns/first-10/bootstrap` with recruiter token works.
4. `POST /webhooks/whatsapp` with service token + signature processes.
5. Restart service and confirm data persistence (`/leads/manual` still populated).

## Auth Tokens (Pilot)
- Recruiter token roles: `["recruiter"]`
- Employer token roles: `["employer"]`
- Service token roles: `["service"]`
- Use short expiry (`exp`) and rotate weekly during pilot.

## On-Call Basics
- If `/health/ready` fails: check database availability and secret rotation.
- If 5xx alert triggers: inspect Cloud Run logs and `/metrics` route breakdown.
- If webhook failures spike: inspect webhook retry status and signature mismatch.

## Rollback
1. `gcloud run revisions list --service hiring-agent-api --region <region>`
2. Shift traffic to last healthy revision.
3. Open incident note with error window and failing endpoints.

