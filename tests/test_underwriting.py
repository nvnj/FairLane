"""Tests for the underwriting reasoner — no real Gemini calls (mocked)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from data.schema import PROTECTED
from agents.underwriting import adjudicate, _parse_and_validate


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_LEGITIMATE = {
    "income": 85000,
    "loan_amount": 300000,
    "debt_to_income_ratio": "38",
    "combined_loan_to_value_ratio": "80.0",
    "property_value": "375000",
    "loan_type": 1,
    "loan_purpose": 1,
    "lien_status": 1,
}

_VALID_RESPONSE_JSON = json.dumps({
    "decision": "approve",
    "recommended_rate": 6.5,
    "recommended_amount": 300000,
    "rationale": "Strong income relative to loan amount and manageable DTI ratio.",
    "key_factors": ["income: 85000", "debt_to_income_ratio: 38"],
})


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


def _patched_client(response_text: str):
    """Context manager: patches _get_client() so no real API call is made."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(response_text)
    return patch("agents.underwriting._get_client", return_value=mock_client)


# ── Schema validation tests (no LLM) ─────────────────────────────────────────

def test_parse_and_validate_approve():
    result = _parse_and_validate(_VALID_RESPONSE_JSON)
    assert result["decision"] == "approve"
    assert isinstance(result["rationale"], str) and result["rationale"]
    assert isinstance(result["key_factors"], list)


def test_parse_and_validate_deny():
    payload = json.dumps({
        "decision": "deny",
        "recommended_rate": None,
        "recommended_amount": None,
        "rationale": "DTI too high.",
        "key_factors": ["debt_to_income_ratio: 55"],
    })
    result = _parse_and_validate(payload)
    assert result["decision"] == "deny"


def test_parse_and_validate_refer():
    payload = json.dumps({
        "decision": "refer",
        "recommended_rate": None,
        "recommended_amount": None,
        "rationale": "Requires manual review.",
        "key_factors": ["loan_amount: 500000"],
    })
    result = _parse_and_validate(payload)
    assert result["decision"] == "refer"


def test_parse_and_validate_invalid_decision_raises():
    # Include all _REQUIRED_KEYS so the missing-key check does not fire first
    payload = json.dumps({
        "decision": "maybe",
        "recommended_rate": None,
        "recommended_amount": None,
        "rationale": "Uncertain.",
        "key_factors": [],
    })
    with pytest.raises(ValueError, match="Invalid decision"):
        _parse_and_validate(payload)


def test_parse_and_validate_missing_key_raises():
    payload = json.dumps({
        "decision": "approve",
        "rationale": "Good profile.",
        # key_factors missing
    })
    with pytest.raises(ValueError, match="missing required keys"):
        _parse_and_validate(payload)


def test_parse_and_validate_strips_fences():
    fenced = "```json\n" + _VALID_RESPONSE_JSON + "\n```"
    result = _parse_and_validate(fenced)
    assert result["decision"] == "approve"


def test_parse_and_validate_bad_json_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_and_validate("not json at all")


# ── adjudicate() contract tests ───────────────────────────────────────────────

def test_adjudicate_returns_valid_schema():
    """adjudicate() returns a dict with the correct schema when Gemini is mocked."""
    with _patched_client(_VALID_RESPONSE_JSON):
        result = adjudicate(_VALID_LEGITIMATE)

    assert result["decision"] in ("approve", "deny", "refer"), (
        f"decision must be one of approve/deny/refer, got {result['decision']!r}"
    )
    assert isinstance(result["rationale"], str) and result["rationale"], (
        "rationale must be a non-empty string"
    )
    assert isinstance(result["key_factors"], list), (
        "key_factors must be a list"
    )


def test_adjudicate_returns_optional_fields():
    """recommended_rate and recommended_amount are present even when null in the response."""
    # Include the fields as null — _REQUIRED_KEYS requires them; setdefault fills None if absent
    payload = json.dumps({
        "decision": "deny",
        "recommended_rate": None,
        "recommended_amount": None,
        "rationale": "High risk.",
        "key_factors": ["DTI: 55"],
    })
    with _patched_client(payload):
        result = adjudicate(_VALID_LEGITIMATE)
    assert "recommended_rate" in result
    assert "recommended_amount" in result


# ── Invariant #2 test — MUST exist and MUST pass ──────────────────────────────

def test_adjudicate_raises_on_protected_attribute_in_input():
    """Invariant #2: adjudicate() must AssertionError if any protected key is present."""
    for protected_key in PROTECTED:
        contaminated = dict(_VALID_LEGITIMATE)
        contaminated[protected_key] = "some_value"
        with pytest.raises(AssertionError, match="Invariant #2"):
            adjudicate(contaminated)


def test_adjudicate_raises_on_multiple_protected_attributes():
    """Invariant #2: even a single protected key in a dict with all keys must be caught."""
    contaminated = dict(_VALID_LEGITIMATE)
    contaminated["derived_race"] = "White"
    contaminated["derived_sex"] = "Male"
    with pytest.raises(AssertionError, match="Invariant #2"):
        adjudicate(contaminated)


def test_adjudicate_clean_features_does_not_raise():
    """Invariant #2 must NOT fire on clean legitimate-only features."""
    with _patched_client(_VALID_RESPONSE_JSON):
        result = adjudicate(_VALID_LEGITIMATE)
    assert result["decision"] in ("approve", "deny", "refer")
