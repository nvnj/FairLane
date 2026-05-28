"""
agent/instrumentation.py

Phoenix tracing setup. Import and call init_tracing() as the VERY FIRST
thing in any entry point (main.py, api/main.py) before any ADK or Gemini call.

register() reads PHOENIX_API_KEY and PHOENIX_COLLECTOR_ENDPOINT from the
environment automatically — do NOT pass them as parameters.
"""

import os

from dotenv import load_dotenv
from phoenix.otel import register

load_dotenv()

_TRACING_INITIALIZED = False
_tracer_provider = None


def init_tracing() -> None:
    global _TRACING_INITIALIZED, _tracer_provider
    if _TRACING_INITIALIZED:
        return

    _tracer_provider = register(
        project_name=os.environ["PHOENIX_PROJECT_NAME"],
        auto_instrument=True,
        batch=True,
        protocol="http/protobuf",
    )
    _TRACING_INITIALIZED = True
    print(f"[phoenix] tracing initialized -> project: {os.environ['PHOENIX_PROJECT_NAME']}")


def flush_traces() -> None:
    if _tracer_provider:
        _tracer_provider.force_flush(timeout_millis=5000)
