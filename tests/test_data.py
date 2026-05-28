"""Tests for data/schema.py split_application function."""

import pytest

from data.schema import LEGITIMATE, PROTECTED, split_application


def _make_row(**overrides) -> dict:
    """Build a complete valid HMDA row fixture."""
    row = {
        "id": "test-001",
        "income": 85000,
        "loan_amount": 300000,
        "debt_to_income_ratio": 0.38,
        "combined_loan_to_value_ratio": 0.80,
        "property_value": 375000,
        "loan_type": 1,
        "loan_purpose": 1,
        "lien_status": 1,
        "derived_race": "White",
        "derived_sex": "Male",
        "derived_ethnicity": "Not Hispanic or Latino",
        "action_taken": 1,
    }
    row.update(overrides)
    return row


def test_split_legitimate_keys_only():
    rec = split_application(_make_row())
    assert set(rec.legitimate.keys()) == set(LEGITIMATE)


def test_split_protected_keys_only():
    rec = split_application(_make_row())
    assert set(rec.protected.keys()) == set(PROTECTED.keys())


def test_split_no_crossover():
    rec = split_application(_make_row())
    crossover = set(rec.legitimate.keys()) & set(rec.protected.keys())
    assert crossover == set(), f"Protected keys leaked into legitimate: {crossover}"


def test_split_protected_not_in_legitimate():
    """Protected attribute values must not appear as keys in the legitimate dict."""
    rec = split_application(_make_row())
    for protected_key in PROTECTED:
        assert protected_key not in rec.legitimate, (
            f"Protected key {protected_key!r} found in legitimate dict"
        )


def test_split_legitimate_values_correct():
    rec = split_application(_make_row())
    assert rec.legitimate["income"] == 85000
    assert rec.legitimate["loan_amount"] == 300000
    assert rec.legitimate["debt_to_income_ratio"] == 0.38


def test_split_missing_legitimate_raises():
    row = _make_row()
    del row["income"]
    with pytest.raises(ValueError, match="income"):
        split_application(row)


def test_split_none_legitimate_raises():
    row = _make_row(income=None)
    with pytest.raises(ValueError, match="income"):
        split_application(row)


def test_split_missing_multiple_raises():
    row = _make_row()
    del row["income"]
    del row["loan_amount"]
    with pytest.raises(ValueError):
        split_application(row)


def test_split_action_taken_stored():
    rec = split_application(_make_row(action_taken=3))
    assert rec.action_taken == 3


def test_split_id_stored():
    rec = split_application(_make_row(id="abc-123"))
    assert rec.id == "abc-123"
