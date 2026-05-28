"""Rolling per-group consistency scorer for bias drift detection.

Reads exclusively from audit_log SQLite — no Phoenix API calls.
The /drift endpoint exposes these stats; Gemini CLI queries Phoenix
via MCP separately to compare experiment runs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "fairlane.db"

_JUDGE_THRESHOLD = float(os.getenv("ESCALATION_JUDGE_THRESHOLD", "0.85"))


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_rolling_consistency(window: int = 50) -> dict:
    """Compute per-protected-group average judge_score over the last `window` audit records.

    Returns:
        {
            "overall_avg": float,
            "by_group": {group_name: avg_score, ...},
            "window_size": int,
            "records_with_flips": int,
            "status": "healthy" | "degraded",
            "proposed_action": str | None,
        }

    Invariant: all arithmetic is Python — Gemini is never called here.
    """
    if not DB_PATH.exists():
        return {
            "overall_avg": 0.0,
            "by_group": {},
            "window_size": 0,
            "records_with_flips": 0,
            "status": "degraded",
            "proposed_action": "No audit_log found. Run make ingest then make eval to populate data.",
        }

    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT metrics, variants FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (window,),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return {
            "overall_avg": 0.0,
            "by_group": {},
            "window_size": 0,
            "records_with_flips": 0,
            "status": "degraded",
            "proposed_action": "audit_log table not found. Run make eval to create records.",
        }
    conn.close()

    if not rows:
        return {
            "overall_avg": 0.0,
            "by_group": {},
            "window_size": 0,
            "records_with_flips": 0,
            "status": "degraded",
            "proposed_action": "No audit records found. Run make eval to generate data.",
        }

    # Accumulate: group_name → list of judge_scores
    group_scores: dict[str, list[float]] = {}
    all_scores: list[float] = []
    records_with_flips = 0

    for row in rows:
        metrics = json.loads(row["metrics"])
        judge_score = float(metrics.get("judge_score", 0.0))
        all_scores.append(judge_score)

        flipped_variants: list[dict] = metrics.get("flipped_variants", [])
        if flipped_variants:
            records_with_flips += 1

        # Group by swept_attribute+swept_value from flipped variants.
        # If there are no flips, attribute the score to every group present in variants.
        if flipped_variants:
            for fv in flipped_variants:
                variant = fv.get("variant", {})
                attr = variant.get("swept_attribute", "")
                val = variant.get("swept_value", "")
                if attr and val:
                    key = f"{attr}:{val}"
                    group_scores.setdefault(key, []).append(judge_score)
        else:
            # No flips — use variant metadata from the variants column
            try:
                variants = json.loads(row["variants"])
            except (json.JSONDecodeError, TypeError):
                variants = []
            for v in variants:
                attr = v.get("swept_attribute", "")
                val = v.get("swept_value", "")
                if attr and val:
                    key = f"{attr}:{val}"
                    group_scores.setdefault(key, []).append(judge_score)

    overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0.0
    by_group = {k: sum(v) / len(v) for k, v in group_scores.items()}

    # Degraded if overall or any group falls below threshold
    degraded = overall_avg < _JUDGE_THRESHOLD or any(
        score < _JUDGE_THRESHOLD for score in by_group.values()
    )

    proposed_action: str | None = None
    if degraded:
        worst_group = min(by_group, key=by_group.__getitem__) if by_group else "unknown"
        proposed_action = (
            f"Consistency score degraded (overall={overall_avg:.3f}, "
            f"worst group={worst_group} score={by_group.get(worst_group, 0.0):.3f}). "
            f"Suggested fix: strengthen the 'demographic neutrality' constraint in "
            f"agents/prompts/underwriting_reasoner.md — add an explicit prohibition like "
            f"'Do NOT reference, infer, or proxy any demographic characteristic in your "
            f"decision or rationale, even indirectly.'"
        )

    return {
        "overall_avg": round(overall_avg, 4),
        "by_group": {k: round(v, 4) for k, v in by_group.items()},
        "window_size": len(rows),
        "records_with_flips": records_with_flips,
        "status": "degraded" if degraded else "healthy",
        "proposed_action": proposed_action,
    }


def _print_report(window: int = 50) -> None:
    result = get_rolling_consistency(window)
    print(f"\nFairLane Drift Report (last {result['window_size']} records)")
    print("=" * 60)
    print(f"Status:             {result['status'].upper()}")
    print(f"Overall avg score:  {result['overall_avg']:.4f}  (threshold: {_JUDGE_THRESHOLD})")
    print(f"Records with flips: {result['records_with_flips']}")
    print(f"\nPer-group scores:")
    if result["by_group"]:
        for group, score in sorted(result["by_group"].items()):
            flag = " ⚠" if score < _JUDGE_THRESHOLD else ""
            print(f"  {group:<50} {score:.4f}{flag}")
    else:
        print("  (no group data yet)")
    if result["proposed_action"]:
        print(f"\nProposed action:\n  {result['proposed_action']}")
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="FairLane drift report")
    parser.add_argument("--report", action="store_true", help="Print rolling consistency report")
    parser.add_argument("--window", type=int, default=50, help="Rolling window size (default: 50)")
    args = parser.parse_args()

    if args.report:
        _print_report(args.window)
    else:
        parser.print_help()
