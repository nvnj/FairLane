"""FastAPI entry point: adjudication, audit retrieval, human approval, drift, and health endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.orchestrator import run_pipeline
from compliance.logger import get_all_records, get_record, record_human_action
from data.ingest_hmda import get_all_applications, get_application, get_sample
from observability.drift_monitor import get_rolling_consistency

app = FastAPI(title="FairLane API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ─────────────────────────────────────────────────

class AdjudicateRequest(BaseModel):
    application_id: str


class ApproveRequest(BaseModel):
    audit_id: str
    action: str          # "approve" | "override" | "send_back"
    officer_note: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/applications")
def list_applications():
    """Return all applications ordered numerically for the console's application selector."""
    apps = get_all_applications()
    return [
        {
            "id": app.id,
            "income": app.legitimate.get("income"),
            "loan_amount": app.legitimate.get("loan_amount"),
            "loan_purpose": app.legitimate.get("loan_purpose"),
        }
        for app in apps
    ]


@app.get("/applications/{app_id}")
def get_application_by_id(app_id: str):
    """Return a single application by ID for the console's default-selection pin."""
    app = get_application(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {app_id!r} not found")
    return {
        "id": app.id,
        "income": app.legitimate.get("income"),
        "loan_amount": app.legitimate.get("loan_amount"),
        "loan_purpose": app.legitimate.get("loan_purpose"),
    }


@app.post("/adjudicate")
def adjudicate_endpoint(body: AdjudicateRequest):
    """Run the full pipeline and return the audit packet. Does NOT finalize — human gate only in /approve."""
    try:
        result = run_pipeline(body.application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@app.get("/audit/{audit_id}")
def get_audit(audit_id: str):
    """Retrieve a full audit record by id."""
    record = get_record(audit_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Audit record {audit_id!r} not found")
    return record


@app.post("/approve")
def approve_endpoint(body: ApproveRequest):
    """Record the human officer's final action. This is the ONLY path that finalizes a decision."""
    valid = {"approve", "override", "send_back"}
    if body.action not in valid:
        raise HTTPException(status_code=422, detail=f"action must be one of {valid}")
    try:
        record_human_action(body.audit_id, body.action, body.officer_note)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "audit_id": body.audit_id,
        "action": body.action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/drift")
def drift_endpoint(window: int = 50):
    """Rolling per-group consistency scores for bias drift detection."""
    return get_rolling_consistency(window)
