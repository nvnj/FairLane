"""Tests for the deterministic counterfactual generator — no LLM calls."""

from __future__ import annotations

import copy

import pytest

from data.schema import LEGITIMATE, PROTECTED, ApplicationRecord
from agents.counterfactual import make_counterfactuals


# ── Fixture ───────────────────────────────────────────────────────────────────

def _make_app(
    race: str = "White",
    sex: str = "Male",
    ethnicity: str = "Not Hispanic or Latino",
) -> ApplicationRecord:
    return ApplicationRecord(
        id="cf-test-001",
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
            "derived_race": race,
            "derived_sex": sex,
            "derived_ethnicity": ethnicity,
        },
        action_taken=1,
    )


_EXPECTED_COUNT = sum(len(v) for v in PROTECTED.values())


# ── Required test 1: exact variant count ─────────────────────────────────────

def test_variant_count_equals_sum_of_protected_values():
    """make_counterfactuals() produces exactly sum(len(v) for v in PROTECTED.values()) variants."""
    app = _make_app()
    variants = make_counterfactuals(app)
    assert len(variants) == _EXPECTED_COUNT, (
        f"Expected {_EXPECTED_COUNT} variants (one per protected value), got {len(variants)}"
    )


# ── Required test 2: legitimate features are byte-identical ──────────────────

def test_legitimate_features_byte_identical_across_all_variants():
    """Every legitimate field in every variant must be byte-identical to the baseline."""
    app = _make_app()
    variants = make_counterfactuals(app)
    for i, variant in enumerate(variants):
        for key in LEGITIMATE:
            assert key in variant, f"Variant {i} missing legitimate key {key!r}"
            assert variant[key] == app.legitimate[key], (
                f"Variant {i} (sweeping {variant.get('swept_attribute')!r}): "
                f"legitimate key {key!r} changed from {app.legitimate[key]!r} "
                f"to {variant[key]!r}"
            )


# ── Required test 3: exactly one protected attribute differs per variant ──────

def test_exactly_one_protected_attribute_differs_per_variant():
    """Each variant changes exactly one protected attribute; all others stay at baseline."""
    app = _make_app()
    variants = make_counterfactuals(app)
    for i, variant in enumerate(variants):
        swept_attr = variant["swept_attribute"]
        swept_val = variant["swept_value"]
        # The swept field must equal swept_value
        assert variant[swept_attr] == swept_val, (
            f"Variant {i}: {swept_attr!r} value {variant[swept_attr]!r} "
            f"doesn't match swept_value {swept_val!r}"
        )
        # All other protected attributes must equal the applicant's baseline
        differing = [
            attr for attr in PROTECTED
            if attr != swept_attr and variant.get(attr) != app.protected.get(attr)
        ]
        assert not differing, (
            f"Variant {i} (sweeping {swept_attr!r}): "
            f"non-swept attributes changed: {differing}"
        )


# ── Additional structural tests ───────────────────────────────────────────────

def test_swept_attribute_and_swept_value_keys_present():
    """Every variant must carry swept_attribute and swept_value metadata keys."""
    app = _make_app()
    variants = make_counterfactuals(app)
    for i, v in enumerate(variants):
        assert "swept_attribute" in v, f"Variant {i} missing 'swept_attribute'"
        assert "swept_value" in v, f"Variant {i} missing 'swept_value'"
        assert v["swept_attribute"] in PROTECTED, (
            f"Variant {i}: swept_attribute {v['swept_attribute']!r} not in PROTECTED"
        )


def test_all_protected_values_are_covered():
    """Every value in every PROTECTED list must appear in exactly one variant."""
    app = _make_app()
    variants = make_counterfactuals(app)
    covered: dict[str, set] = {attr: set() for attr in PROTECTED}
    for v in variants:
        covered[v["swept_attribute"]].add(v["swept_value"])
    for attr, values in PROTECTED.items():
        assert covered[attr] == set(values), (
            f"Protected attribute {attr!r}: expected values {set(values)}, "
            f"got {covered[attr]}"
        )


def test_no_variant_shares_reference_with_another():
    """Mutating one variant's legitimate dict must not affect any other variant."""
    app = _make_app()
    variants = make_counterfactuals(app)
    original_income = app.legitimate["income"]
    variants[0]["income"] = 999999
    for i in range(1, len(variants)):
        assert variants[i]["income"] == original_income, (
            f"Variant {i} was aliased: mutating variant 0 changed variant {i}"
        )


def test_no_cross_product_generated():
    """Total variant count must not grow to the cross-product size."""
    app = _make_app()
    variants = make_counterfactuals(app)
    cross_product_size = 1
    for values in PROTECTED.values():
        cross_product_size *= len(values)
    # For our PROTECTED dict, cross-product would be 5*2*2=20; sum is 9
    assert len(variants) < cross_product_size, (
        "Variants appear to be a cross-product — should sweep one attribute at a time"
    )
    assert len(variants) == _EXPECTED_COUNT
