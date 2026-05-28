"""Writes adjudication audit records to SQLite audit_log; the only component that finalizes human officer actions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "fairlane.db"

_VALID_HUMAN_ACTIONS = {"approve", "override", "send_back"}


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            baseline_decision TEXT NOT NULL,
            variants TEXT NOT NULL,
            variant_decisions TEXT NOT NULL,
            metrics TEXT NOT NULL,
            packet TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            human_action TEXT,
            officer_note TEXT,
            created_at TEXT NOT NULL,
            finalized_at TEXT
        )
    """)
    conn.commit()


def log_adjudication(
    id: str,
    application_id: str,
    baseline_decision: dict,
    variants: list[dict],
    variant_decisions: list[dict],
    metrics: dict,
    packet: dict,
    trace_id: str,
) -> None:
    """Persist the full adjudication record to audit_log. Does not finalize — human action required."""
    conn = _get_connection()
    _ensure_table(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO audit_log
            (id, application_id, baseline_decision, variants, variant_decisions,
             metrics, packet, trace_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id,
            application_id,
            json.dumps(baseline_decision),
            json.dumps(variants),
            json.dumps(variant_decisions),
            json.dumps(metrics),
            json.dumps(packet),
            trace_id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def record_human_action(id: str, action: str, officer_note: str = "") -> None:
    """Record the loan officer's final action. This is the ONLY path that finalizes a decision."""
    if action not in _VALID_HUMAN_ACTIONS:
        raise ValueError(f"Invalid action {action!r}. Must be one of {_VALID_HUMAN_ACTIONS}")

    conn = _get_connection()
    _ensure_table(conn)
    conn.execute(
        """
        UPDATE audit_log
        SET human_action = ?, officer_note = ?, finalized_at = ?
        WHERE id = ?
        """,
        (action, officer_note, datetime.now(timezone.utc).isoformat(), id),
    )
    if conn.execute("SELECT changes()").fetchone()[0] == 0:
        conn.close()
        raise ValueError(f"No audit record found with id {id!r}")
    conn.commit()
    conn.close()


def get_record(id: str) -> Optional[dict]:
    """Retrieve one audit record by id; return None if not found."""
    conn = _get_connection()
    _ensure_table(conn)
    row = conn.execute(
        "SELECT * FROM audit_log WHERE id = ?", (id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None
    return _row_to_dict(row)


def get_all_records(limit: int = 100) -> list[dict]:
    """Return the most recent audit records up to limit."""
    conn = _get_connection()
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("baseline_decision", "variants", "variant_decisions", "metrics", "packet"):
        if d.get(key):
            d[key] = json.loads(d[key])
    return d
