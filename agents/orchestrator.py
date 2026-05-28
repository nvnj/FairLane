"""Coordinator: runs the full 5-step adjudication pipeline per loan application and owns the Phoenix trace context."""

from __future__ import annotations

import argparse
import os
import uuid

from opentelemetry import trace

from observability.phoenix_setup import init_tracing
from data.ingest_hmda import get_application, get_sample
from data.schema import ApplicationRecord
from agents.underwriting import adjudicate, adjudicate_batch
from agents.counterfactual import make_counterfactuals
from agents.disparity import run_disparity_analysis, apply_judge_threshold
from agents.router import write_packet
from compliance.logger import log_adjudication
from observability.evals import run_consistency_eval

tracer = trace.get_tracer(__name__)


def run_pipeline(application_id: str) -> dict:
    """Run the full adjudication pipeline for one application.

    Returns:
        {audit_id, application_id, packet, metrics, trace_id}

    The pipeline produces a recommendation only. Nothing is finalized until
    a human officer calls POST /approve.
    """
    # Step 1: tracing must be initialized before any Gemini call
    init_tracing()

    with tracer.start_as_current_span("fairlane_pipeline") as pipeline_span:
        pipeline_span.set_attribute("application_id", application_id)

        # Step 2: load application
        app = get_application(application_id)
        if app is None:
            raise ValueError(f"Application {application_id!r} not found in DB")

        # Step 3: baseline underwriting decision (legitimate features only)
        baseline_decision = adjudicate(app.legitimate)

        # Step 4: generate counterfactual variants (deterministic, no LLM)
        variants = make_counterfactuals(app)

        # Step 5: batch underwriting decisions for all variants
        variant_decisions = adjudicate_batch(variants)

        # Step 6: deterministic disparity metrics
        metrics = run_disparity_analysis(baseline_decision, variants, variant_decisions)

        # Step 7: LLM-as-judge consistency eval (logs to Phoenix trace)
        judge_score = run_consistency_eval(baseline_decision, variants, variant_decisions)

        # Step 8: merge judge_score into metrics and re-apply full escalation rule
        metrics = apply_judge_threshold(metrics, judge_score)

        pipeline_span.set_attribute("flip_rate", metrics["flip_rate"])
        pipeline_span.set_attribute("judge_score", metrics["judge_score"])
        pipeline_span.set_attribute("recommended_action", metrics["recommended_action"])

        # Step 9: write human-facing packet (router copies recommended_action, never recomputes)
        packet = write_packet(baseline_decision, metrics, app)

        # Step 10: persist audit record
        audit_id = str(uuid.uuid4())
        trace_id = format(pipeline_span.get_span_context().trace_id, "032x")

        # Serialize variants for storage (remove non-JSON-serializable refs if any)
        log_adjudication(
            id=audit_id,
            application_id=application_id,
            baseline_decision=baseline_decision,
            variants=variants,
            variant_decisions=variant_decisions,
            metrics=metrics,
            packet=packet,
            trace_id=trace_id,
        )

        # Step 11: return result packet
        return {
            "audit_id": audit_id,
            "application_id": application_id,
            "packet": packet,
            "metrics": metrics,
            "trace_id": trace_id,
        }


def _demo() -> None:
    """Demo mode: pick an application, force escalation, print the full packet."""
    print("FairLane demo — forcing escalation to show the hero moment\n")

    # Force escalation by setting threshold to -1 (any flip_rate > -1 escalates)
    os.environ["ESCALATION_FLIP_THRESHOLD"] = "-1"

    sample = get_sample(5)
    if not sample:
        print("ERROR: No records in DB. Run: make ingest")
        return

    # Pick the first application with a deny to make flips likely
    app = next((a for a in sample if a.action_taken == 3), sample[0])
    print(f"Selected application id={app.id!r}")
    print(f"  income={app.legitimate.get('income')}, "
          f"DTI={app.legitimate.get('debt_to_income_ratio')}, "
          f"LTV={app.legitimate.get('combined_loan_to_value_ratio')}")
    print(f"  protected: {app.protected}\n")

    result = run_pipeline(app.id)
    packet = result["packet"]
    metrics = result["metrics"]

    print("=" * 60)
    print(f"HEADLINE: {packet.get('headline')}")
    print(f"ACTION:   {packet.get('recommended_action')}")
    print(f"\nSUMMARY:\n{packet.get('summary')}")
    print(f"\nEVIDENCE:")
    for e in packet.get("evidence", []):
        print(f"  - {e}")
    print(f"\nNEXT STEPS:")
    for s in packet.get("next_steps", []):
        print(f"  - {s}")
    print(f"\nMETRICS:")
    print(f"  flip_rate:          {metrics['flip_rate']:.3f}")
    print(f"  approval_rate_gap:  {metrics['approval_rate_gap']:.3f}")
    print(f"  terms_gap:          {metrics['terms_gap']:.3f}")
    print(f"  judge_score:        {metrics['judge_score']:.3f}")
    print(f"\nAudit ID:  {result['audit_id']}")
    print(f"Trace ID:  {result['trace_id']}")
    print(f"\nCheck Phoenix: {os.environ.get('PHOENIX_COLLECTOR_ENDPOINT', '')}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FairLane orchestrator")
    parser.add_argument("--demo", action="store_true", help="Run scripted demo scenario")
    args = parser.parse_args()

    if args.demo:
        _demo()
    else:
        parser.print_help()
