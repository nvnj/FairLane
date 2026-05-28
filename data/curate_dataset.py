"""Curate a 30-application evaluation dataset and run scored experiments logged to Phoenix.

Dataset segments:
  - 10 borderline DTI: debt_to_income_ratio in the 40-50% range
  - 10 thin-file:      income present but loan_amount is high relative to income (LTV >= 0.8),
                       AND combined_loan_to_value_ratio >= 0.8
  - 10 mixed-signal:   approved (action_taken=1) applicants whose DTI is also in the 40-50% band
                       (approved despite borderline DTI → the model is most likely to flip)

Experiment logging:
  run_experiment(prompt_version) runs the full pipeline on all 30 apps and logs the run
  as a named Phoenix dataset/experiment so the Gemini CLI can compare versions via MCP.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "fairlane.db"

# ── DTI parsing ────────────────────────────────────────────────────────────────

def _parse_dti(val) -> Optional[float]:
    """Return a float midpoint for FFIEC DTI bucket strings or plain floats/ints.

    FFIEC publishes DTI as strings like '40%-<50%', '20%-<30%', 'NA'.
    We map each bucket to its midpoint for range comparisons.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s.lower() in ("na", "exempt", ""):
        return None
    # Numeric string
    try:
        return float(s.rstrip("%"))
    except ValueError:
        pass
    # FFIEC bucket pattern: '40%-<50%'
    import re
    m = re.match(r"(\d+)%-?<(\d+)%", s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo + hi) / 2.0
    # Single-bound like '>60%'
    m2 = re.match(r">(\d+)%", s)
    if m2:
        return float(m2.group(1)) + 5.0
    m3 = re.match(r"<(\d+)%", s)
    if m3:
        return float(m3.group(1)) - 5.0
    return None


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _load_all_applications() -> list[dict]:
    """Return all rows from the applications table as plain dicts."""
    if not DB_PATH.exists():
        return []
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT id, legitimate, protected, action_taken FROM applications"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    result = []
    for row in rows:
        try:
            result.append({
                "id": row["id"],
                "legitimate": json.loads(row["legitimate"]),
                "protected": json.loads(row["protected"]),
                "action_taken": row["action_taken"],
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return result


# ── Segment selectors ──────────────────────────────────────────────────────────

def _select_borderline_dti(apps: list[dict], n: int) -> list[dict]:
    """Select apps with DTI midpoint in [40, 50)."""
    candidates = []
    for a in apps:
        dti = _parse_dti(a["legitimate"].get("debt_to_income_ratio"))
        if dti is not None and 40.0 <= dti < 50.0:
            candidates.append(a)
    return candidates[:n]


def _select_thin_file(apps: list[dict], n: int) -> list[dict]:
    """Select apps with combined_loan_to_value_ratio >= 0.8 (thin equity / high leverage).

    HMDA 'thin-file' proxy: no credit score in public data, so we use high LTV
    as the closest available signal for under-collateralised / risky profiles.
    """
    candidates = []
    for a in apps:
        ltv_raw = a["legitimate"].get("combined_loan_to_value_ratio")
        try:
            ltv = float(ltv_raw)
        except (TypeError, ValueError):
            continue
        if ltv >= 80.0:
            candidates.append(a)
    return candidates[:n]


def _select_mixed_signal(apps: list[dict], n: int) -> list[dict]:
    """Select ORIGINATED (action_taken=1) apps that also have borderline DTI (40-50%).

    These are the most interesting: approved despite borderline DTI.
    The model is most likely to flip on demographic variants for this segment.
    """
    candidates = []
    for a in apps:
        if a["action_taken"] != 1:
            continue
        dti = _parse_dti(a["legitimate"].get("debt_to_income_ratio"))
        if dti is not None and 40.0 <= dti < 50.0:
            candidates.append(a)
    return candidates[:n]


# ── Dataset curation ───────────────────────────────────────────────────────────

def curate_eval_dataset(
    n_per_segment: int = 10,
) -> tuple[list[dict], dict[str, int]]:
    """Return (app_list, segment_counts) for the evaluation dataset.

    Fills each segment greedily; if a segment is under-filled it is padded with
    random records from the remaining pool so the experiment always runs on real data.
    """
    all_apps = _load_all_applications()
    if not all_apps:
        raise RuntimeError(
            "No application records found. Run: make ingest"
        )

    borderline = _select_borderline_dti(all_apps, n_per_segment)
    thin_file = _select_thin_file(all_apps, n_per_segment)
    mixed = _select_mixed_signal(all_apps, n_per_segment)

    # De-duplicate by id, preserving order
    seen: set[str] = set()
    combined: list[dict] = []
    for app in borderline + thin_file + mixed:
        if app["id"] not in seen:
            seen.add(app["id"])
            combined.append(app)

    # Pad to 30 if we got fewer unique apps
    target = n_per_segment * 3
    if len(combined) < target:
        for app in all_apps:
            if len(combined) >= target:
                break
            if app["id"] not in seen:
                seen.add(app["id"])
                combined.append(app)

    counts = {
        "borderline_dti": len(borderline),
        "thin_file": len(thin_file),
        "mixed_signal": len(mixed),
        "total_unique": len(combined),
    }
    return combined, counts


# ── Experiment runner ──────────────────────────────────────────────────────────

def run_experiment(prompt_version: str, n_per_segment: int = 10) -> dict:
    """Run the full pipeline on the curated dataset; return a summary dict.

    Each run_pipeline() call writes a Phoenix trace automatically via OpenInference
    instrumentation. The experiment name is embedded as a span attribute so Phoenix
    can group traces by experiment for the Gemini CLI comparison.

    Returns:
        {
            "experiment_name": str,
            "total": int,
            "completed": int,
            "failed": int,
            "avg_judge_score": float,
            "avg_flip_rate": float,
            "escalated": int,
            "prompt_version": str,
            "timestamp": str,
        }
    """
    # Import here so this module can be imported without tracing initialized
    from observability.phoenix_setup import init_tracing
    from agents.orchestrator import run_pipeline
    from opentelemetry import trace as otel_trace

    init_tracing()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    experiment_name = f"fairlane-eval-{prompt_version}-{timestamp}"

    apps, counts = curate_eval_dataset(n_per_segment)
    logger.info(
        "Starting experiment %s — %d apps (%s)",
        experiment_name,
        len(apps),
        counts,
    )

    tracer = otel_trace.get_tracer(__name__)
    judge_scores: list[float] = []
    flip_rates: list[float] = []
    escalated = 0
    completed = 0
    failed = 0

    for app in apps:
        with tracer.start_as_current_span("experiment_run") as span:
            span.set_attribute("experiment.name", experiment_name)
            span.set_attribute("experiment.prompt_version", prompt_version)
            span.set_attribute("application.id", app["id"])
            try:
                result = run_pipeline(app["id"])
                metrics = result.get("metrics", {})
                judge_scores.append(float(metrics.get("judge_score", 0.0)))
                flip_rates.append(float(metrics.get("flip_rate", 0.0)))
                if metrics.get("recommended_action") == "escalate":
                    escalated += 1
                completed += 1
                span.set_attribute("result.judge_score", metrics.get("judge_score", 0.0))
                span.set_attribute("result.flip_rate", metrics.get("flip_rate", 0.0))
                span.set_attribute("result.recommended_action", metrics.get("recommended_action", ""))
            except Exception as exc:
                logger.warning("Pipeline failed for app %s: %s", app["id"], exc)
                span.set_attribute("result.error", str(exc))
                failed += 1

    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0
    avg_flip = sum(flip_rates) / len(flip_rates) if flip_rates else 0.0

    summary = {
        "experiment_name": experiment_name,
        "total": len(apps),
        "completed": completed,
        "failed": failed,
        "avg_judge_score": round(avg_judge, 4),
        "avg_flip_rate": round(avg_flip, 4),
        "escalated": escalated,
        "prompt_version": prompt_version,
        "timestamp": timestamp,
        "segment_counts": counts,
    }

    logger.info(
        "Experiment %s done — avg_judge=%.3f avg_flip=%.3f escalated=%d/%d",
        experiment_name,
        avg_judge,
        avg_flip,
        escalated,
        completed,
    )
    return summary


# ── CLI ────────────────────────────────────────────────────────────────────────

def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="FairLane evaluation dataset curator")
    parser.add_argument(
        "--run-experiment",
        action="store_true",
        help="Run the full eval pipeline on the curated 30-app dataset",
    )
    parser.add_argument(
        "--prompt-version",
        default="v1",
        help="Prompt version label for the experiment name (default: v1)",
    )
    parser.add_argument(
        "--n-per-segment",
        type=int,
        default=10,
        help="Apps per segment: borderline_dti, thin_file, mixed_signal (default: 10)",
    )
    parser.add_argument(
        "--show-dataset",
        action="store_true",
        help="Print selected application IDs and segments without running the pipeline",
    )
    args = parser.parse_args()

    if args.show_dataset:
        apps, counts = curate_eval_dataset(args.n_per_segment)
        print(f"\nCurated eval dataset ({counts['total_unique']} apps)")
        print(f"  borderline_dti: {counts['borderline_dti']}")
        print(f"  thin_file:      {counts['thin_file']}")
        print(f"  mixed_signal:   {counts['mixed_signal']}")
        print(f"\nApplication IDs:")
        for a in apps:
            print(f"  {a['id']}  dti={a['legitimate'].get('debt_to_income_ratio')}  "
                  f"ltv={a['legitimate'].get('combined_loan_to_value_ratio')}  "
                  f"action={a['action_taken']}")
        return

    if args.run_experiment:
        summary = run_experiment(
            prompt_version=args.prompt_version,
            n_per_segment=args.n_per_segment,
        )
        print(f"\nExperiment: {summary['experiment_name']}")
        print(f"  Completed: {summary['completed']}/{summary['total']}  Failed: {summary['failed']}")
        print(f"  avg judge score: {summary['avg_judge_score']:.4f}")
        print(f"  avg flip rate:   {summary['avg_flip_rate']:.4f}")
        print(f"  escalated:       {summary['escalated']}")
        print(f"\nSegments: {summary['segment_counts']}")
        print(f"\nTraces visible in Phoenix under project: {summary['experiment_name']}")
        return

    parser.print_help()


if __name__ == "__main__":
    _main()
