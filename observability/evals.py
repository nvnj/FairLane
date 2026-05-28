"""LLM-as-judge consistency eval and deterministic code eval, logged as Phoenix eval annotations on the active trace."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from opentelemetry import trace

load_dotenv()

_JUDGE_PROMPT_PATH = Path(__file__).parent.parent / "agents" / "prompts" / "disparity_judge.md"
_JUDGE_PROMPT: str = _JUDGE_PROMPT_PATH.read_text(encoding="utf-8")

_JUDGE_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "consistency_score": types.Schema(type=types.Type.NUMBER),
        "decisions_match":   types.Schema(type=types.Type.BOOLEAN),
        "terms_equivalent":  types.Schema(type=types.Type.BOOLEAN),
        "rationale_flags":   types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        "explanation":       types.Schema(type=types.Type.STRING),
    },
    required=["consistency_score", "decisions_match", "terms_equivalent", "rationale_flags", "explanation"],
)


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


def _log_eval_to_span(span: trace.Span, eval_name: str, score: float, label: str, explanation: str = "") -> None:
    """Attach eval annotation attributes to the current OpenTelemetry span."""
    span.set_attribute(f"eval.{eval_name}.score", score)
    span.set_attribute(f"eval.{eval_name}.label", label)
    if explanation:
        span.set_attribute(f"eval.{eval_name}.explanation", explanation[:500])


def run_consistency_eval(
    baseline: dict,
    variants: list[dict],
    variant_decisions: list[dict],
) -> float:
    """Run both a deterministic code eval and an LLM-as-judge eval; return the judge's consistency_score.

    Invariant #1: score arithmetic is in Python. Gemini only reads rationales and returns a score.
    Both evals are logged as span attributes on the current active trace.
    """
    tracer = trace.get_tracer(__name__)
    current_span = trace.get_current_span()

    # --- Deterministic code eval: do all decisions literally match? ---
    baseline_decision = baseline.get("decision", "")
    all_match = all(vd.get("decision") == baseline_decision for vd in variant_decisions)
    code_score = 1.0 if all_match else 0.0
    _log_eval_to_span(
        current_span,
        "decision_match",
        score=code_score,
        label="pass" if all_match else "fail",
        explanation=f"All {len(variant_decisions)} variant decisions match baseline ({baseline_decision})" if all_match
                    else f"Some variants differ from baseline ({baseline_decision})",
    )

    # --- LLM-as-judge eval ---
    user_payload = {
        "baseline": {
            "decision": baseline.get("decision"),
            "recommended_rate": baseline.get("recommended_rate"),
            "recommended_amount": baseline.get("recommended_amount"),
            "rationale": baseline.get("rationale"),
            "key_factors": baseline.get("key_factors"),
        },
        "variants": [
            {
                "swept_attribute": v.get("swept_attribute"),
                "swept_value": v.get("swept_value"),
                "decision": vd.get("decision"),
                "recommended_rate": vd.get("recommended_rate"),
                "recommended_amount": vd.get("recommended_amount"),
                "rationale": vd.get("rationale"),
                "key_factors": vd.get("key_factors"),
            }
            for v, vd in zip(variants, variant_decisions)
        ],
    }

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = _get_client()

    with tracer.start_as_current_span("disparity_judge_eval") as span:
        response = client.models.generate_content(
            model=model,
            contents=json.dumps(user_payload, indent=2),
            config=types.GenerateContentConfig(
                system_instruction=_JUDGE_PROMPT,
                response_mime_type="application/json",
                response_schema=_JUDGE_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )

        raw = response.text
        try:
            result = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Judge returned invalid JSON: {exc}\nRaw: {raw!r}") from exc

        score = float(result.get("consistency_score", 0.0))
        explanation = result.get("explanation", "")
        flags = result.get("rationale_flags", [])

        _log_eval_to_span(
            span,
            "consistency",
            score=score,
            label="pass" if score >= float(os.getenv("ESCALATION_JUDGE_THRESHOLD", "0.85")) else "fail",
            explanation=explanation,
        )
        if flags:
            span.set_attribute("eval.consistency.rationale_flags", json.dumps(flags))

        span.set_attribute("eval.consistency.decisions_match", result.get("decisions_match", False))
        span.set_attribute("eval.consistency.terms_equivalent", result.get("terms_equivalent", False))

    return score
