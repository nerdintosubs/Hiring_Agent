# Compliance and Risk Notes (Bengaluru)

## Data and Privacy
- Capture explicit consent before storing candidate identity or certificates.
- Store only required PII and enforce retention windows (default target: 180 days).
- Redact PII from logs, analytics exports, and test fixtures.

## Hiring Fairness
- Do not rank candidates using protected attributes.
- Keep explainable scoring fields (`therapy`, `language`, `commute`, `cert/experience`).
- Track recruiter overrides for periodic bias audit.

## Operational Safety
- Require recruiter approval before final offer issuance.
- Use idempotent webhook handling to avoid duplicate candidate actions.
- Add background check workflow before joining confirmation in production.

## Labor and Policy
- Validate shift plans and compensation against Karnataka labor guidance.
- Ensure workplace safety and POSH policy acknowledgement in onboarding.
- Keep legal review checkpoints for employment terms and contractor models.

