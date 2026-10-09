"""LLM-as-judge for eval tests.

Usage in tests:
    score = judge(
        criterion="The code implements the regularised MSE loss",
        context=unit.raw,
        output=generated_code,
    )
    assert score >= 0.7
"""

from __future__ import annotations

import json

import litellm
from pydantic import BaseModel, Field

_DEFAULT_MODEL = "gpt-4o-mini"

_SYSTEM = """\
You are an impartial evaluator judging whether a piece of output satisfies a criterion.

You will receive:
- criterion: what the output should do
- context: reference material (e.g. the LaTeX spec the output was derived from)
- output: the thing being judged

Respond with a JSON object only — no markdown fences:
{
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}

Scoring guide:
  1.0 — fully satisfies the criterion
  0.7 — mostly satisfies with minor gaps
  0.5 — partially satisfies
  0.3 — attempts but misses the core requirement
  0.0 — does not satisfy at all
"""


class _Verdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


def judge(
    criterion: str,
    context: str,
    output: str,
    *,
    model: str = _DEFAULT_MODEL,
    threshold: float | None = None,
) -> float:
    """Score *output* against *criterion* using an LLM judge.

    Returns a 0-1 float. If *threshold* is given, raises AssertionError when
    the score falls below it (so `judge(..., threshold=0.7)` works as a
    pytest assertion).
    """
    user_msg = f"criterion: {criterion}\n\ncontext:\n{context}\n\noutput:\n{output}"
    try:
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
        )
    except Exception as exc:
        _msg = str(exc).lower()
        if any(tok in _msg for tok in ("api key", "api_key", "credentials", "authentication", "unauthorized")):
            import pytest
            pytest.skip(f"no API key configured for model '{model}' — {exc}")
        raise
    raw = response.choices[0].message.content or ""
    try:
        verdict = _Verdict.model_validate(json.loads(raw))
    except Exception as exc:
        raise ValueError(f"judge returned unparseable response: {raw!r}") from exc

    if threshold is not None and verdict.score < threshold:
        raise AssertionError(
            f"judge score {verdict.score:.2f} < {threshold} — {verdict.reasoning}"
        )
    return verdict.score
