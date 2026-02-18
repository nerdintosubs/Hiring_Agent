REGION ?= asia-south1
SERVICE_NAME ?= hiring-agent-api
AUTH_MODE ?= enabled

.PHONY: lint test smoke-local release

lint:
	python -m ruff check .

test:
	python -m pytest -q

smoke-local:
	python scripts/smoke_test.py --base-url http://127.0.0.1:8000 --auth-mode disabled

release:
	@test -n "$(PROJECT_ID)" || (echo "Set PROJECT_ID=<gcp-project-id>" && exit 1)
	PROJECT_ID="$(PROJECT_ID)" REGION="$(REGION)" SERVICE_NAME="$(SERVICE_NAME)" AUTH_MODE="$(AUTH_MODE)" RELEASE_TOKEN="$(RELEASE_TOKEN)" bash scripts/release.sh

