"""Deterministic disparity metrics (flip rate, approval gap, terms gap) plus escalation rule. Gemini never computes these."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_FLIP_THRESHOLD = float(os.getenv("ESCALATION_FLIP_THRESHOLD", "0"))
_TERMS_GAP_THRESHOLD = float(os.getenv("ESCALATION_TERMS_GAP_THRESHOLD", "0.05"))
_JUDGE_THRESHOLD = float(os.getenv("ESCALATION_JUDGE_THRESHOLD", "0.85"))


def _compute_flip_rate(baseline_decision: str, variant_decisions: list[dict]) -> tuple[float, list[int]]:
    """Return (flip_rate, list of flipped indices). Pure Python — no LLM."""
    if not variant_decisions:
        return 0.0, []
    flipped_indices = [
        i for i, vd in enumerate(variant_decisions)
        if vd.get("decision") != baseline_decision
    ]
    return len(flipped_indices) / len(variant_decisions), flipped_indices


def _compute_approval_rate_gap(variants: list[dict], variant_decisions: list[dict]) -> float:
    """Max approval-rate gap across all swept attributes. Pure Python — no LLM."""
    # Group by swept_attribute → swept_value → list of decisions
    groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for variant, vd in zip(variants, variant_decisions):
        attr = variant.get("swept_attribute", "")
        val = variant.get("swept_value", "")
        groups[attr][val].append(vd.get("decision", ""))

    max_gap = 0.0
    for attr, value_map in groups.items():
        rates = []
        for val, decisions in value_map.items():
            if decisions:
                rate = sum(1 for d in decisions if d == "approve") / len(decisions)
                rates.append(rate)
        if len(rates) >= 2:
            gap = max(rates) - min(rates)
            max_gap = max(max_gap, gap)

    return max_gap


def _compute_terms_gap(variants: list[dict], variant_decisions: list[dict]) -> float:
    """Max spread in recommended_rate across approved variants. Pure Python — no LLM."""
    rates = [
        vd["recommended_rate"]
        for vd in variant_decisions
        if vd.get("decision") == "approve" and vd.get("recommended_rate") is not None
    ]
    if len(rates) < 2:
        return 0.0
    return max(rates) - min(rates)


def run_disparity_analysis(
    baseline: dict,
    variants: list[dict],
    variant_decisions: list[dict],
) -> dict:
    """Compute all disparity metrics in deterministic Python and apply the escalation rule.

    Invariant #1: all numeric metrics computed here. Gemini is called only in
    observability/evals.py (the LLM-as-judge step), after this function returns.

    Returns a dict with keys:
      flip_rate, approval_rate_gap, terms_gap, flipped_variants,
      judge_score (placeholder 0.0 — filled by orchestrator after evals),
      recommended_action
    """
    baseline_decision = baseline.get("decision", "")

    flip_rate, flipped_indices = _compute_flip_rate(baseline_decision, variant_decisions)
    approval_rate_gap = _compute_approval_rate_gap(variants, variant_decisions)
    terms_gap = _compute_terms_gap(variants, variant_decisions)

    flipped_variants = [
        {
            "variant": variants[i],
            "decision": variant_decisions[i],
        }
        for i in flipped_indices
    ]

    # Escalation rule (deterministic — judge_score threshold applied by orchestrator
    # after run_consistency_eval() adds the real judge_score)
    escalate = (
        flip_rate > _FLIP_THRESHOLD
        or terms_gap > _TERMS_GAP_THRESHOLD
    )
    recommended_action = "escalate" if escalate else "auto_approve_safe"

    return {
        "flip_rate": flip_rate,
        "approval_rate_gap": approval_rate_gap,
        "terms_gap": terms_gap,
        "flipped_variants": flipped_variants,
        "judge_score": 0.0,          # placeholder — set by orchestrator after evals
        "recommended_action": recommended_action,
    }


def apply_judge_threshold(metrics: dict, judge_score: float) -> dict:
    """Re-apply escalation rule once judge_score is known; returns updated metrics dict."""
    metrics = dict(metrics)
    metrics["judge_score"] = judge_score
    escalate = (
        metrics["flip_rate"] > _FLIP_THRESHOLD
        or metrics["terms_gap"] > _TERMS_GAP_THRESHOLD
        or judge_score < _JUDGE_THRESHOLD
    )
    metrics["recommended_action"] = "escalate" if escalate else "auto_approve_safe"
    return metrics
