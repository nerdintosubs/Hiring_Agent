# Architecture Overview

## Hosting Split
- Frontend dashboard: Netlify (`frontend/`)
- API + workflow engine: GCP Cloud Run (`backend/`)
- Database: Cloud SQL (PostgreSQL in production; in-memory store for local bootstrap)
- Async/events: Pub/Sub (placeholder in this bootstrap)

## Core Modules
- `backend/app/main.py`: FastAPI entrypoint and endpoints
- `backend/app/store.py`: in-memory persistence, stage transitions, audit events
- `backend/app/persistence.py`: SQLite persistence for webhook retry state and manual lead inbox
- `backend/app/services/scoring.py`: Bengaluru fit scoring (therapy, language, commute, cert/experience)
- `backend/app/services/dedupe.py`: duplicate candidate detection

## Lifecycle Covered
1. Employer intake
2. Candidate ingestion (all channels)
3. Screening + hard filters
4. Interview scheduling
5. Shortlist generation
6. Offer creation
7. Pipeline visibility
8. First-10 female fresher onboarding campaign tracking
9. Manual lead inbox (walk-ins/calls/referrals) for no-provider operation

## Next Production Upgrades
- Replace in-memory store with PostgreSQL + SQLAlchemy.
- Move screening/interview reminders to worker queues.
- Add provider adapters for WhatsApp and telephony APIs.
- Add auth and role-based access control for recruiters/employers.
