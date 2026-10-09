"""
Worker tests use a mock _completion to avoid real LLM calls.
The mock returns a minimal valid JSON response.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from latex_ia.models import Profile, Role, Unit
from latex_ia.worker import _extract_json, process_unit


def _mock_completion(role: str = "spec", confidence: float = 0.9, **extra):
    payload = {
        "role": role,
        "confidence": confidence,
        "reasoning": "test reasoning",
        "code_stub": "def f(): pass  # spec: test",
        "test_stub": "def test_f(): assert f() is None",
        "open_questions": [],
        **extra,
    }
    msg = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def _unit(id_: str = "algorithm", marked: bool = False) -> Unit:
    return Unit(id=id_, hash="abc", raw="\\begin{algorithm}\\end{algorithm}", marked=marked)


def _profile() -> Profile:
    return Profile(field="machine-learning", model="gpt-4o-mini")


class TestExtractJson:
    def test_plain_json(self):
        data = _extract_json('{"role": "spec", "confidence": 0.9}')
        assert data["role"] == "spec"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"role": "spec"}\n```'
        data = _extract_json(raw)
        assert data["role"] == "spec"

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError):
            _extract_json("no json here")


class TestProcessUnit:
    def test_returns_unit_result(self):
        completion = MagicMock(return_value=_mock_completion("spec"))
        unit = _unit()
        result = process_unit(unit, [unit], _profile(), _completion=completion)
        assert result.role == Role.spec
        assert result.confidence == pytest.approx(0.9)
        assert completion.called

    def test_passes_model_to_completion(self):
        completion = MagicMock(return_value=_mock_completion())
        process_unit(_unit(), [_unit()], _profile(), _completion=completion)
        call_kwargs = completion.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    def test_bad_role_falls_back_to_unknown(self):
        completion = MagicMock(return_value=_mock_completion(role="not_a_role"))
        result = process_unit(_unit(), [_unit()], _profile(), _completion=completion)
        assert result.role == Role.unknown
        assert result.confidence == 0.0

    def test_open_questions_propagated(self):
        completion = MagicMock(
            return_value=_mock_completion(open_questions=["What is lambda?"])
        )
        result = process_unit(_unit(), [_unit()], _profile(), _completion=completion)
        assert "What is lambda?" in result.open_questions
