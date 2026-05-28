"""API integration tests using httpx.AsyncClient + pytest-asyncio."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from compliance.logger import log_adjudication


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_pipeline_result(application_id: str = "test-app-001") -> dict:
    """A canned pipeline result that matches the real schema."""
    audit_id = str(uuid.uuid4())
    return {
        "audit_id": audit_id,
        "application_id": application_id,
        "packet": {
            "headline": "Decision flips on race — escalate",
            "recommended_action": "escalate",
            "summary": "The baseline decision changes when race is varied. Human review required.",
            "evidence": ["derived_race: flip from deny to approve"],
            "next_steps": ["Review application manually", "Document decision rationale"],
        },
        "metrics": {
            "flip_rate": 0.333,
            "approval_rate_gap": 0.5,
            "terms_gap": 0.0,
            "flipped_variants": [],
            "judge_score": 0.1,
            "recommended_action": "escalate",
        },
        "trace_id": "a" * 32,
    }


def _seed_audit_record(audit_id: str, application_id: str = "seed-app") -> None:
    """Directly write a record to audit_log so approve/get tests don't depend on Gemini."""
    log_adjudication(
        id=audit_id,
        application_id=application_id,
        baseline_decision={"decision": "deny", "recommended_rate": None, "recommended_amount": None,
                           "rationale": "High DTI", "key_factors": ["DTI: 45"]},
        variants=[],
        variant_decisions=[],
        metrics={"flip_rate": 0.0, "approval_rate_gap": 0.0, "terms_gap": 0.0,
                 "flipped_variants": [], "judge_score": 0.95, "recommended_action": "auto_approve_safe"},
        packet={"headline": "Consistent", "recommended_action": "auto_approve_safe",
                "summary": "No bias detected.", "evidence": [], "next_steps": []},
        trace_id="b" * 32,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_healthz():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_adjudicate_returns_packet_with_headline():
    fake = _fake_pipeline_result("app-42")
    with patch("api.main.run_pipeline", return_value=fake):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/adjudicate", json={"application_id": "app-42"})
    assert resp.status_code == 200
    body = resp.json()
    assert "headline" in body["packet"]
    assert "audit_id" in body
    assert "metrics" in body


@pytest.mark.asyncio
async def test_adjudicate_404_on_missing_app():
    with patch("api.main.run_pipeline", side_effect=ValueError("not found")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/adjudicate", json={"application_id": "bad-id"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_records_action():
    audit_id = str(uuid.uuid4())
    _seed_audit_record(audit_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/approve",
            json={"audit_id": audit_id, "action": "approve", "officer_note": "Looks good"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "approve"
    assert body["audit_id"] == audit_id
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_get_audit_human_action_matches():
    audit_id = str(uuid.uuid4())
    _seed_audit_record(audit_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Record action
        await client.post(
            "/approve",
            json={"audit_id": audit_id, "action": "override", "officer_note": "Manual override"},
        )
        # Retrieve and verify
        resp = await client.get(f"/audit/{audit_id}")

    assert resp.status_code == 200
    record = resp.json()
    assert record["human_action"] == "override"
    assert record["officer_note"] == "Manual override"


@pytest.mark.asyncio
async def test_get_audit_404_on_missing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/audit/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_invalid_action_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/approve",
            json={"audit_id": "any", "action": "delete"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_drift_returns_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/drift")
    assert resp.status_code == 200
    assert "status" in resp.json()
