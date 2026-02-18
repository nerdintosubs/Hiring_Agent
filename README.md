# Hiring Agent (Bengaluru Wellness)

Bootstrap implementation of a multilingual, hyperlocal hiring agent for spas, ayurvedic centers, and therapy providers.

## Quick start
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m uvicorn backend.app.main:app --reload
```

## Useful commands
```bash
python -m pytest -q
python -m ruff check .
docker compose up --build
make smoke-local
```

## Key paths
- `backend/app/main.py` FastAPI endpoints and lifecycle handlers
- `backend/app/store.py` application state, stage transitions, audit trail
- `backend/app/services/` dedupe + scoring + workflow rules
- `tests/backend/` API and business-logic tests
- `frontend/` Netlify-hosted dashboard bootstrap
- `docs/` architecture and compliance notes

## First-10 onboarding APIs
- `POST /campaigns/first-10/bootstrap` start a Bengaluru female-fresher onboarding sprint
- `POST /campaigns/{campaign_id}/events` log funnel events (`leads`, `screened`, `trials`, `offers`, `joined`)
- `GET /campaigns/{campaign_id}/progress` view conversion rates and next recommended actions

## Webhook notes
- `POST /webhooks/whatsapp` supports `X-Hub-Signature-256` (`sha256=<hmac>`) when `WHATSAPP_WEBHOOK_SECRET` is set.
- `POST /webhooks/telephony` supports `X-Telephony-Signature` or `X-Provider-Signature` when `TELEPHONY_WEBHOOK_SECRET` is set.
- Both endpoints track idempotency and retry state (`processed`, `retry_pending`, `failed`, `duplicate`).

## Manual lead inbox APIs
- `POST /leads/manual` create walk-in/call/referral leads without external providers.
- `GET /leads/manual?limit=50` list recent manual leads.
- `GET /leads/manual` supports filters: `source_channel`, `neighborhood`, `created_by`, `search`, `created_from`, `created_to`.

## Website therapist funnel APIs
- `POST /leads/website` public website intake endpoint (returns SLA due time + `wa.me` link).
- `GET /leads/website` recruiter queue with `queue_mode=all|due_soon|overdue|hot_new`.
- `POST /leads/website/{lead_id}/contact` mark first recruiter contact and compute SLA breach.
- `POST /events/website` capture website funnel events (`view`, `cta_click`, `form_start`, `form_submit`, `wa_click`).
- `GET /funnel/website/summary` recruiter analytics for leads, SLA, source, and neighborhood mix.
- Optional anti-bot: include `recaptcha_token` in `POST /leads/website` and enable server verification via env vars below.

## Dashboard
- `frontend/index.html` now includes:
- campaign KPI panel
- manual lead inbox form + recent leads table

## Local simulator
```bash
python scripts/mock_webhooks.py --channel whatsapp --count 10
python scripts/mock_webhooks.py --channel telephony --count 5 --event-type call_lead
python scripts/generate_jwt.py --secret dev-secret --subject recruiter-1 --roles recruiter
```

## Instagram outreach ops automation (compliant workflow)
```bash
# 1) Generate daily capture sheet from seed accounts
python scripts/instagram_outreach_automation.py --mode plan --seeds refreshdspa,tiaradoorstep --per-seed 50

# 2) After filling captured handles manually, ingest into lead inbox + create outreach queue
JWT_SECRET=<jwt-secret> python scripts/instagram_outreach_automation.py --mode ingest --input-csv data/instagram_capture_sheet.csv --api-base <api-url> --campaign-id <cmp_id>
```

## Persistence
- SQLite persistence is enabled by default via `PERSISTENCE_ENABLED=true`.
- Path is configurable with `PERSISTENCE_DB_PATH` (default `data/hiring_agent.sqlite3`).
- Webhook retries/events and manual lead inbox entries survive restarts.
- For production, set `DATABASE_URL` to PostgreSQL (for example `postgresql+psycopg://...`).
- Full in-memory workflow state is snapshotted to SQL so jobs/candidates/offers survive restarts.

## SLA configuration
- Global default first-contact SLA for website leads: `DEFAULT_FIRST_CONTACT_SLA_MINUTES` (default `30`, allowed `5..240`).
- Per-campaign override via `POST /campaigns/first-10/bootstrap` field: `first_contact_sla_minutes`.

## reCAPTCHA configuration
- `RECAPTCHA_ENABLED=true` enables server-side verification on `POST /leads/website`.
- `RECAPTCHA_SECRET=<google-secret>` must be set when enabled.
- `RECAPTCHA_MIN_SCORE` controls acceptance threshold (default `0.5`).

## Auth and Roles
- Set `AUTH_ENABLED=true` to enforce JWT auth.
- Token payload requires:
- `sub`: user/service id
- `roles`: array (for example `["recruiter"]`, `["employer"]`, `["service"]`)
- Protected endpoint groups:
- recruiter/admin: lead inbox, screening, shortlist, offers, campaigns
- employer/recruiter/admin: intake and pipeline
- service/admin: webhooks

## Production Deploy
- Build and deploy Cloud Run service via `infra/gcp/cloudrun/deploy.sh`.
- Use runbook: `docs/runbook_pilot.md`.
- Enable alerts with `infra/gcp/monitoring/alert-policy.yaml`.

## One-Command Release
- Bash (lint + tests + deploy + smoke):
```bash
PROJECT_ID=<gcp-project-id> REGION=asia-south1 AUTH_MODE=enabled bash scripts/release.sh
```
- PowerShell wrapper:
```powershell
.\scripts\release.ps1 -ProjectId <gcp-project-id> -Region asia-south1 -AuthMode enabled
```
- Make target:
```bash
make release PROJECT_ID=<gcp-project-id> REGION=asia-south1 AUTH_MODE=enabled
```
- Optional authenticated smoke check: provide token as `RELEASE_TOKEN` (bash/make) or `-ReleaseToken` (PowerShell).
