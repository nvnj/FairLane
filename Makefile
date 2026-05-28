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
	gcloud run deploy fairlane `
>>   --source . `
>>   --region us-central1 `
>>   --allow-unauthenticated `
>>   --set-env-vars="GOOGLE_CLOUD_PROJECT=fairlane-hackathon,GOOGLE_CLOUD_LOCATION=us,PHOENIX_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJBcGlLZXk6NiJ9.Q3lmOBF6sY7JUxmplq4tiPT2Xa2U4DXSxNJFjNwzzjw,PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/naveenjohn2k,PHOENIX_PROJECT_NAME=FairLane,GEMINI_MODEL=gemini-3.5-flash,ESCALATION_FLIP_THRESHOLD=0,ESCALATION_JUDGE_THRESHOLD=0.85,ESCALATION_TERMS_GAP_THRESHOLD=0.05"

drift-report:
	uv run python -m observability.drift_monitor --report
