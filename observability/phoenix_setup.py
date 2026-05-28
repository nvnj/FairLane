"""Phoenix Cloud tracing initialization via OpenInference; must be called first in every entry point."""

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
