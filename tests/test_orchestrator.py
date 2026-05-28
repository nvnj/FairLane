"""Tests for the orchestrator pipeline — mocks all Gemini calls; deterministic functions run real."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data.schema import ApplicationRecord, PROTECTED
from compliance.logger import DB_PATH


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_app(app_id: str = "orch-test-001") -> ApplicationRecord:
    return ApplicationRecord(
        id=app_id,
        legitimate={
            "income": 90000,
            "loan_amount": 280000,
            "debt_to_income_ratio": "35",
            "combined_loan_to_value_ratio": "78.0",
            "property_value": "360000",
            "loan_type": 1,
            "loan_purpose": 1,
            "lien_status": 1,
        },
        protected={
            "derived_race": "White",
            "derived_sex": "Male",
            "derived_ethnicity": "Not Hispanic or Latino",
        },
        action_taken=1,
    )


def _fake_underwriting_decision(decision: str = "approve") -> dict:
    return {
        "decision": decision,
        "recommended_rate": 6.25,
        "recommended_amount": 280000,
        "rationale": "Strong income and low DTI.",
        "key_factors": ["income: 90000", "debt_to_income_ratio: 35"],
    }


def _fake_packet() -> dict:
    return {
        "headline": "No bias detected — safe to approve",
        "recommended_action": "auto_approve_safe",
        "summary": "Counterfactual sweep found no decision flips or terms gaps.",
        "evidence": ["All demographic variants received approve"],
        "next_steps": ["Proceed with standard documentation"],
    }


def _all_mocks(app_id: str = "orch-test-001"):
    """Return a dict of all patch targets needed to isolate run_pipeline from external calls."""
    app = _make_app(app_id)
    baseline = _fake_underwriting_decision("approve")
    # One variant decision per protected value (9 total)
    n_variants = sum(len(v) for v in PROTECTED.values())
    variant_decisions = [_fake_underwriting_decision("approve") for _ in range(n_variants)]

    return {
        "agents.orchestrator.init_tracing": MagicMock(),
        "agents.orchestrator.get_application": MagicMock(return_value=app),
        "agents.orchestrator.adjudicate": MagicMock(return_value=baseline),
        "agents.orchestrator.adjudicate_batch": MagicMock(return_value=variant_decisions),
        "agents.orchestrator.run_consistency_eval": MagicMock(return_value=0.95),
        "agents.orchestrator.write_packet": MagicMock(return_value=_fake_packet()),
    }


# ── Test: run_pipeline() returns the correct top-level keys ──────────────────

def test_run_pipeline_returns_required_keys():
    """run_pipeline() must return a dict with audit_id, packet, metrics, trace_id."""
    app_id = f"orch-{uuid.uuid4()}"
    mocks = _all_mocks(app_id)

    with (
        patch("agents.orchestrator.init_tracing", mocks["agents.orchestrator.init_tracing"]),
        patch("agents.orchestrator.get_application", mocks["agents.orchestrator.get_application"]),
        patch("agents.orchestrator.adjudicate", mocks["agents.orchestrator.adjudicate"]),
        patch("agents.orchestrator.adjudicate_batch", mocks["agents.orchestrator.adjudicate_batch"]),
        patch("agents.orchestrator.run_consistency_eval", mocks["agents.orchestrator.run_consistency_eval"]),
        patch("agents.orchestrator.write_packet", mocks["agents.orchestrator.write_packet"]),
    ):
        from agents.orchestrator import run_pipeline
        result = run_pipeline(app_id)

    assert isinstance(result, dict), "run_pipeline() must return a dict"
    for key in ("audit_id", "packet", "metrics", "trace_id"):
        assert key in result, f"run_pipeline() result missing required key {key!r}"


def test_run_pipeline_result_values_have_correct_types():
    """audit_id and trace_id are strings; packet and metrics are dicts."""
    app_id = f"orch-{uuid.uuid4()}"
    mocks = _all_mocks(app_id)

    with (
        patch("agents.orchestrator.init_tracing", mocks["agents.orchestrator.init_tracing"]),
        patch("agents.orchestrator.get_application", mocks["agents.orchestrator.get_application"]),
        patch("agents.orchestrator.adjudicate", mocks["agents.orchestrator.adjudicate"]),
        patch("agents.orchestrator.adjudicate_batch", mocks["agents.orchestrator.adjudicate_batch"]),
        patch("agents.orchestrator.run_consistency_eval", mocks["agents.orchestrator.run_consistency_eval"]),
        patch("agents.orchestrator.write_packet", mocks["agents.orchestrator.write_packet"]),
    ):
        from agents.orchestrator import run_pipeline
        result = run_pipeline(app_id)

    assert isinstance(result["audit_id"], str) and result["audit_id"]
    assert isinstance(result["trace_id"], str) and result["trace_id"]
    assert isinstance(result["packet"], dict)
    assert isinstance(result["metrics"], dict)


def test_run_pipeline_metrics_has_required_keys():
    """metrics dict must contain flip_rate, approval_rate_gap, terms_gap, judge_score, recommended_action."""
    app_id = f"orch-{uuid.uuid4()}"
    mocks = _all_mocks(app_id)

    with (
        patch("agents.orchestrator.init_tracing", mocks["agents.orchestrator.init_tracing"]),
        patch("agents.orchestrator.get_application", mocks["agents.orchestrator.get_application"]),
        patch("agents.orchestrator.adjudicate", mocks["agents.orchestrator.adjudicate"]),
        patch("agents.orchestrator.adjudicate_batch", mocks["agents.orchestrator.adjudicate_batch"]),
        patch("agents.orchestrator.run_consistency_eval", mocks["agents.orchestrator.run_consistency_eval"]),
        patch("agents.orchestrator.write_packet", mocks["agents.orchestrator.write_packet"]),
    ):
        from agents.orchestrator import run_pipeline
        result = run_pipeline(app_id)

    metrics = result["metrics"]
    for key in ("flip_rate", "approval_rate_gap", "terms_gap", "judge_score", "recommended_action"):
        assert key in metrics, f"metrics missing key {key!r}"


# ── Test: audit record is written to SQLite after run_pipeline() ──────────────

def test_run_pipeline_writes_audit_record_to_sqlite():
    """After run_pipeline(), the audit_id must appear in the SQLite audit_log table."""
    app_id = f"orch-{uuid.uuid4()}"
    mocks = _all_mocks(app_id)

    with (
        patch("agents.orchestrator.init_tracing", mocks["agents.orchestrator.init_tracing"]),
        patch("agents.orchestrator.get_application", mocks["agents.orchestrator.get_application"]),
        patch("agents.orchestrator.adjudicate", mocks["agents.orchestrator.adjudicate"]),
        patch("agents.orchestrator.adjudicate_batch", mocks["agents.orchestrator.adjudicate_batch"]),
        patch("agents.orchestrator.run_consistency_eval", mocks["agents.orchestrator.run_consistency_eval"]),
        patch("agents.orchestrator.write_packet", mocks["agents.orchestrator.write_packet"]),
    ):
        from agents.orchestrator import run_pipeline
        result = run_pipeline(app_id)

    audit_id = result["audit_id"]

    # Read directly from SQLite — do not go through the logger API
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, application_id FROM audit_log WHERE id = ?", (audit_id,)
    ).fetchone()
    conn.close()

    assert row is not None, (
        f"No audit_log row found for audit_id={audit_id!r} after run_pipeline()"
    )
    assert row[0] == audit_id
    assert row[1] == app_id


def test_run_pipeline_audit_record_contains_trace_id():
    """The audit record's trace_id column must match what run_pipeline() returned."""
    app_id = f"orch-{uuid.uuid4()}"
    mocks = _all_mocks(app_id)

    with (
        patch("agents.orchestrator.init_tracing", mocks["agents.orchestrator.init_tracing"]),
        patch("agents.orchestrator.get_application", mocks["agents.orchestrator.get_application"]),
        patch("agents.orchestrator.adjudicate", mocks["agents.orchestrator.adjudicate"]),
        patch("agents.orchestrator.adjudicate_batch", mocks["agents.orchestrator.adjudicate_batch"]),
        patch("agents.orchestrator.run_consistency_eval", mocks["agents.orchestrator.run_consistency_eval"]),
        patch("agents.orchestrator.write_packet", mocks["agents.orchestrator.write_packet"]),
    ):
        from agents.orchestrator import run_pipeline
        result = run_pipeline(app_id)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT trace_id FROM audit_log WHERE id = ?", (result["audit_id"],)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == result["trace_id"]


def test_run_pipeline_raises_on_unknown_application():
    """run_pipeline() must raise ValueError when the application is not found."""
    with (
        patch("agents.orchestrator.init_tracing"),
        patch("agents.orchestrator.get_application", return_value=None),
    ):
        from agents.orchestrator import run_pipeline
        with pytest.raises(ValueError, match="not found"):
            run_pipeline("does-not-exist")
