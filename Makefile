.PHONY: setup ingest run-api run-console eval demo test deploy drift-report

setup:
	uv sync

ingest:
	uv run python -m data.ingest_hmda

run-api:
	uv run uvicorn api.main:app --reload --port 8000

run-console:
	cd console && npm run dev

PROMPT_VERSION ?= v1

eval:
	uv run python -m data.curate_dataset --run-experiment --prompt-version $(PROMPT_VERSION)

demo:
	uv run python -m agents.orchestrator --demo

test:
	uv run pytest tests/ -v

deploy:
	gcloud run deploy fairlane --source . --region us-central1 --allow-unauthenticated

drift-report:
	uv run python -m observability.drift_monitor --report
