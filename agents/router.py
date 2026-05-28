"""Decision router: Gemini writes the human-facing review packet; copies recommended_action from disparity metrics, never recomputes it."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from opentelemetry import trace

from data.schema import ApplicationRecord

load_dotenv()

_PROMPT_PATH = Path(__file__).parent / "prompts" / "decision_router.md"
_SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "recommended_action": {"type": "string", "enum": ["auto_approve_safe", "escalate"]},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "recommended_action", "summary", "evidence", "next_steps"],
}

_REQUIRED_KEYS = {"headline", "recommended_action", "summary", "evidence", "next_steps"}

tracer = trace.get_tracer(__name__)


def _get_client() -> genai.Client:
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def write_packet(
    baseline_decision: dict,
    metrics: dict,
    app: ApplicationRecord,
) -> dict:
    """Write the human-facing review packet.

    Critical invariant: recommended_action is COPIED from metrics["recommended_action"].
    The router explains the action; it does not decide it.
    """
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = _get_client()

    # The action is already determined — we pass it explicitly so Gemini copies it
    deterministic_action = metrics["recommended_action"]

    user_message = json.dumps(
        {
            "baseline_decision": baseline_decision,
            "disparity_metrics": {
                "flip_rate": metrics.get("flip_rate"),
                "approval_rate_gap": metrics.get("approval_rate_gap"),
                "terms_gap": metrics.get("terms_gap"),
                "judge_score": metrics.get("judge_score"),
                "recommended_action": deterministic_action,
                "flipped_variants": [
                    {
                        "swept_attribute": fv["variant"].get("swept_attribute"),
                        "swept_value": fv["variant"].get("swept_value"),
                        "decision": fv["decision"].get("decision"),
                    }
                    for fv in metrics.get("flipped_variants", [])
                ],
            },
            "application_context": {
                "id": app.id,
                "legitimate": app.legitimate,
            },
        },
        indent=2,
    )

    with tracer.start_as_current_span("decision_router") as span:
        span.set_attribute("application_id", app.id)
        span.set_attribute("recommended_action_in", deterministic_action)

        response = client.models.generate_content(
            model=model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.2,
            ),
        )

        raw = response.text
        try:
            result = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Router returned invalid JSON: {exc}\nRaw response: {raw!r}"
            ) from exc

        missing = _REQUIRED_KEYS - result.keys()
        if missing:
            raise ValueError(f"Router response missing keys {missing}. Got: {list(result.keys())}")

        # Critical invariant: overwrite whatever Gemini wrote with the deterministic value
        result["recommended_action"] = deterministic_action

        span.set_attribute("headline", result.get("headline", ""))
        span.set_attribute("recommended_action_out", result["recommended_action"])

    return result
