# Repository Guidelines

## Project Structure & Module Organization
This repository is currently in bootstrap stage. Use the structure below for all new contributions so the codebase stays predictable:

- `src/` application code
- `src/agent/` orchestration, prompts, and hiring workflows
- `src/integrations/` connectors (WhatsApp, sheets/CRM, job boards)
- `src/models/` schemas and data contracts
- `tests/` unit and integration tests matching `src/`
- `scripts/` local utilities (seed data, import/export, one-off ops)
- `docs/` architecture notes and product specs

Keep modules small and domain-focused (intake, sourcing, screening, interviews, offers, retention).

## Build, Test, and Development Commands
Standardize on Python tooling:

- `python -m venv .venv` create local environment
- `.venv\Scripts\Activate.ps1` activate on PowerShell
- `pip install -r requirements.txt -r requirements-dev.txt` install runtime + dev dependencies
- `pytest -q` run all tests
- `ruff check .` lint
- `ruff format .` format code

If a command is added or changed, update this file in the same PR.

## Coding Style & Naming Conventions
- Use 4-space indentation and type hints for new Python code.
- File/module names: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Prefer pure functions for scoring/matching logic; isolate side effects in integration modules.

## Testing Guidelines
- Framework: `pytest`
- Place tests under `tests/` mirroring source paths (example: `src/agent/intake.py` -> `tests/agent/test_intake.py`).
- Test names: `test_<behavior>`.
- Add tests for every bug fix and for each workflow stage touched.
- Minimum expectation for PRs: all tests pass locally.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- Keep commits focused; avoid mixing refactors with behavior changes.
- PRs should include:
- concise problem statement
- summary of changes
- test evidence (`pytest -q` output or equivalent)
- linked issue/task ID when available

## Security & Configuration Tips
- Never commit secrets. Use `.env` and provide `.env.example`.
- Mask candidate/employer PII in logs, fixtures, screenshots, and test data.
