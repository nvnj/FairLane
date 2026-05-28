"""Fetches HMDA LAR data from the FFIEC API, normalizes it, and stores applications in local SQLite."""

from __future__ import annotations

import argparse
import io
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

from data.schema import (
    HMDA_ACTION_CODES,
    LEGITIMATE,
    PROTECTED,
    ApplicationRecord,
    split_application,
)

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "fairlane.db"
FFIEC_URL = "https://ffiec.cfpb.gov/v2/data-browser-api/view/csv"

# Maps our schema keys → actual FFIEC CSV column names.
# combined_loan_to_value_ratio is published as loan_to_value_ratio in the FFIEC LAR.
_FFIEC_COLUMN_MAP: dict[str, str] = {
    "income": "income",
    "loan_amount": "loan_amount",
    "debt_to_income_ratio": "debt_to_income_ratio",
    "combined_loan_to_value_ratio": "loan_to_value_ratio",   # FFIEC name differs
    "property_value": "property_value",
    "loan_type": "loan_type",
    "loan_purpose": "loan_purpose",
    "lien_status": "lien_status",
    "derived_race": "derived_race",
    "derived_sex": "derived_sex",
    "derived_ethnicity": "derived_ethnicity",
}


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            legitimate TEXT NOT NULL,
            protected TEXT NOT NULL,
            action_taken INTEGER NOT NULL
        )
    """)
    conn.commit()


def _normalize_value(val):
    """Convert pandas NA / 'Exempt' to None; keep everything else (including DTI bucket strings)."""
    if pd.isna(val):
        return None
    if isinstance(val, str) and val.strip().lower() in ("exempt", "na", ""):
        return None
    return val


def _fetch_hmda_csv(states: str, years: str, limit: int) -> pd.DataFrame:
    """Download HMDA LAR CSV from FFIEC and return as a DataFrame (capped at limit rows)."""
    params = {
        "states": states,
        "years": years,
        "actions_taken": "1,3",
    }
    logger.info("Fetching HMDA data from FFIEC: %s", params)
    response = httpx.get(FFIEC_URL, params=params, timeout=120.0, follow_redirects=True)
    response.raise_for_status()

    df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    logger.info("Downloaded %d rows from FFIEC", len(df))

    if limit:
        df = df.head(limit)

    return df


def _df_to_records(df: pd.DataFrame) -> list[ApplicationRecord]:
    """Normalize DataFrame rows into ApplicationRecord objects; skip rows with missing legitimate features."""
    records: list[ApplicationRecord] = []
    skipped = 0

    for idx, row in df.iterrows():
        raw: dict = {"action_taken": int(row.get("action_taken", 0)), "id": str(idx)}

        for schema_key, ffiec_col in _FFIEC_COLUMN_MAP.items():
            if ffiec_col in df.columns:
                raw[schema_key] = _normalize_value(row[ffiec_col])

        try:
            record = split_application(raw)
            records.append(record)
        except ValueError as exc:
            logger.debug("Skipping row %s: %s", idx, exc)
            skipped += 1

    if skipped:
        logger.warning("Skipped %d rows missing legitimate features", skipped)

    return records


def ingest(states: str = "TX", years: str = "2023", limit: int = 500) -> int:
    """Fetch HMDA data and write to SQLite; return count of records stored."""
    df = _fetch_hmda_csv(states, years, limit)
    records = _df_to_records(df)

    conn = _get_connection()
    _ensure_table(conn)

    inserted = 0
    for rec in records:
        conn.execute(
            "INSERT OR REPLACE INTO applications (id, legitimate, protected, action_taken) VALUES (?, ?, ?, ?)",
            (rec.id, json.dumps(rec.legitimate), json.dumps(rec.protected), rec.action_taken),
        )
        inserted += 1

    conn.commit()
    conn.close()
    logger.info("Stored %d application records in %s", inserted, DB_PATH)
    return inserted


def get_application(id: str) -> Optional[ApplicationRecord]:
    """Retrieve one ApplicationRecord by id from SQLite; return None if not found."""
    conn = _get_connection()
    _ensure_table(conn)
    row = conn.execute(
        "SELECT id, legitimate, protected, action_taken FROM applications WHERE id = ?", (id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None
    return ApplicationRecord(
        id=row[0],
        legitimate=json.loads(row[1]),
        protected=json.loads(row[2]),
        action_taken=row[3],
    )


def get_all_applications() -> list[ApplicationRecord]:
    """Return all ApplicationRecords from SQLite, ordered numerically by id."""
    conn = _get_connection()
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT id, legitimate, protected, action_taken FROM applications ORDER BY CAST(id AS INTEGER)"
    ).fetchall()
    conn.close()
    return [
        ApplicationRecord(
            id=r[0],
            legitimate=json.loads(r[1]),
            protected=json.loads(r[2]),
            action_taken=r[3],
        )
        for r in rows
    ]


def get_sample(n: int = 10) -> list[ApplicationRecord]:
    """Return up to n ApplicationRecords sampled randomly from the SQLite store."""
    conn = _get_connection()
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT id, legitimate, protected, action_taken FROM applications ORDER BY RANDOM() LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()

    return [
        ApplicationRecord(
            id=r[0],
            legitimate=json.loads(r[1]),
            protected=json.loads(r[2]),
            action_taken=r[3],
        )
        for r in rows
    ]


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Ingest HMDA data from FFIEC into local SQLite")
    parser.add_argument("--states", default="TX", help="Comma-separated state codes (default: TX)")
    parser.add_argument("--years", default="2023", help="Comma-separated years (default: 2023)")
    parser.add_argument("--limit", type=int, default=500, help="Max rows to fetch (default: 500)")
    args = parser.parse_args()

    count = ingest(states=args.states, years=args.years, limit=args.limit)
    print(f"\nIngested {count} records into {DB_PATH}")

    sample = get_sample(1)
    if sample:
        rec = sample[0]
        print(f"\nSample record id={rec.id!r}")
        print("  legitimate:", rec.legitimate)
        print("  protected: ", rec.protected)
        print(
            "  action_taken:",
            rec.action_taken,
            f"({HMDA_ACTION_CODES.get(rec.action_taken, 'unknown')})",
        )

        # Verify invariant: no crossover between legitimate and protected keys
        crossover = set(rec.legitimate) & set(rec.protected)
        assert not crossover, f"BUG: crossover keys found: {crossover}"
        assert set(rec.legitimate) == set(LEGITIMATE), "BUG: legitimate keys mismatch"
        assert set(rec.protected) == set(PROTECTED), "BUG: protected keys mismatch"
        print("\nlegitimate/protected split verified - no crossover")


if __name__ == "__main__":
    _main()
