"""Tests for counterfactual generator and disparity metrics — no LLM calls."""

import copy

import pytest

from data.schema import LEGITIMATE, PROTECTED, ApplicationRecord
from agents.counterfactual import make_counterfactuals
from agents.disparity import run_disparity_analysis


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_app() -> ApplicationRecord:
    return ApplicationRecord(
        id="test-001",
        legitimate={
            "income": 85000,
            "loan_amount": 300000,
            "debt_to_income_ratio": "38",
            "combined_loan_to_value_ratio": "80.0",
            "property_value": "375000",
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


def _baseline_decision(decision: str = "approve") -> dict:
    return {
        "decision": decision,
        "recommended_rate": 6.5,
        "recommended_amount": 300000,
        "rationale": "Good income and manageable DTI.",
        "key_factors": ["income: 85000", "debt_to_income_ratio: 38"],
    }


def _variant_decision(decision: str = "approve", rate: float = 6.5) -> dict:
    return {
        "decision": decision,
        "recommended_rate": rate if decision == "approve" else None,
        "recommended_amount": 300000 if decision == "approve" else None,
        "rationale": "Consistent with baseline.",
        "key_factors": ["income: 85000"],
    }


# ── Counterfactual generator tests ───────────────────────────────────────────

def test_variant_count_equals_protected_values_sum():
    app = _make_app()
    variants = make_counterfactuals(app)
    expected = sum(len(v) for v in PROTECTED.values())
    assert len(variants) == expected, f"Expected {expected} variants, got {len(variants)}"


def test_legitimate_features_byte_identical():
    app = _make_app()
    variants = make_counterfactuals(app)
    for i, variant in enumerate(variants):
        for key in LEGITIMATE:
            assert variant[key] == app.legitimate[key], (
                f"Variant {i}: legitimate key {key!r} differs from baseline"
            )


def test_legitimate_not_mutated_across_variants():
    """Mutating one variant's legitimate field must not affect another."""
    app = _make_app()
    variants = make_counterfactuals(app)
    variants[0]["income"] = 999999
    for i in range(1, len(variants)):
        assert variants[i]["income"] == app.legitimate["income"], (
            f"Variant {i} was mutated when variant 0 was changed"
        )


def test_exactly_one_attribute_differs_per_variant():
    """Each variant sweeps exactly one protected attribute away from baseline."""
    app = _make_app()
    variants = make_counterfactuals(app)
    for variant in variants:
        swept_attr = variant["swept_attribute"]
        swept_val = variant["swept_value"]
        # The swept attribute must match the swept_value field
        assert variant[swept_attr] == swept_val
        # All other protected attributes must be at baseline values
        for attr in PROTECTED:
            if attr != swept_attr:
                assert variant[attr] == app.protected[attr], (
                    f"Non-swept attribute {attr!r} changed in variant sweeping {swept_attr!r}"
                )


def test_swept_attribute_and_value_keys_present():
    app = _make_app()
    variants = make_counterfactuals(app)
    for v in variants:
        assert "swept_attribute" in v
        assert "swept_value" in v
        assert v["swept_attribute"] in PROTECTED


# ── Disparity metrics tests ───────────────────────────────────────────────────

def test_flip_rate_zero_when_all_match():
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    vdecisions = [_variant_decision("approve") for _ in variants]
    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert metrics["flip_rate"] == 0.0
    assert metrics["recommended_action"] == "auto_approve_safe"
    assert metrics["flipped_variants"] == []


def test_flip_rate_and_escalation_on_injected_flip():
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    # Inject one flip — first variant is denied
    vdecisions = [_variant_decision("approve") for _ in variants]
    vdecisions[0] = _variant_decision("deny")

    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert metrics["flip_rate"] > 0
    assert metrics["recommended_action"] == "escalate"
    assert len(metrics["flipped_variants"]) == 1


def test_flipped_variants_contains_correct_variant():
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    vdecisions = [_variant_decision("approve") for _ in variants]
    vdecisions[2] = _variant_decision("deny")  # third variant flips

    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert len(metrics["flipped_variants"]) == 1
    flipped = metrics["flipped_variants"][0]
    assert flipped["variant"] == variants[2]
    assert flipped["decision"]["decision"] == "deny"


def test_approval_rate_gap_known_values():
    """Hand-craft a scenario where derived_race has a known approval gap."""
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")

    # Build decisions: approve all race variants except "Black or African American"
    vdecisions = []
    for v in variants:
        if v["swept_attribute"] == "derived_race" and v["swept_value"] == "Black or African American":
            vdecisions.append(_variant_decision("deny"))
        else:
            vdecisions.append(_variant_decision("approve"))

    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    # Gap should be > 0: some race values get approve, one gets deny
    assert metrics["approval_rate_gap"] > 0.0


def test_approval_rate_gap_zero_when_all_approve():
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    vdecisions = [_variant_decision("approve") for _ in variants]
    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert metrics["approval_rate_gap"] == 0.0


def test_terms_gap_zero_when_all_same_rate():
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    vdecisions = [_variant_decision("approve", rate=6.5) for _ in variants]
    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert metrics["terms_gap"] == 0.0


def test_terms_gap_detected():
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    vdecisions = [_variant_decision("approve", rate=6.5) for _ in variants]
    # Give one variant a much higher rate
    vdecisions[0] = _variant_decision("approve", rate=8.0)
    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert abs(metrics["terms_gap"] - 1.5) < 0.001


def test_escalation_on_terms_gap_threshold():
    """terms_gap above threshold escalates even when flip_rate == 0."""
    app = _make_app()
    variants = make_counterfactuals(app)
    baseline = _baseline_decision("approve")
    vdecisions = [_variant_decision("approve", rate=6.5) for _ in variants]
    vdecisions[0] = _variant_decision("approve", rate=6.5 + 0.06)  # just over 0.05 threshold
    metrics = run_disparity_analysis(baseline, variants, vdecisions)
    assert metrics["flip_rate"] == 0.0
    assert metrics["terms_gap"] > 0.05
    assert metrics["recommended_action"] == "escalate"
