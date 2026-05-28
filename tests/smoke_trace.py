"""Smoke test: calls the underwriting reasoner on a real DB record and verifies a Phoenix trace is emitted."""

import json
import os
import sys

# Must be first — initializes tracing before any ADK/Gemini call
from observability.phoenix_setup import init_tracing
init_tracing()

from data.ingest_hmda import get_sample
from agents.underwriting import adjudicate


def main() -> None:
    sample = get_sample(1)
    if not sample:
        print("ERROR: No records in DB. Run: uv run python -m data.ingest_hmda --limit 50")
        sys.exit(1)

    app = sample[0]
    print(f"Testing application id={app.id!r}")
    print("  legitimate:", app.legitimate)

    result = adjudicate(app.legitimate)
    print("\nDecision JSON:")
    print(json.dumps(result, indent=2))

    print(f"\nCheck Phoenix at {os.environ['PHOENIX_COLLECTOR_ENDPOINT']} for the trace")

    # Invariant #2 test: passing protected attributes must raise AssertionError
    poisoned = {**app.legitimate, **app.protected}
    try:
        adjudicate(poisoned)
        print("\nFAIL: adjudicate() accepted protected attributes — invariant #2 is broken!")
        sys.exit(1)
    except AssertionError as exc:
        print(f"\nInvariant #2 verified: adjudicate() correctly rejected protected attributes")
        print(f"  AssertionError: {exc}")


if __name__ == "__main__":
    main()
