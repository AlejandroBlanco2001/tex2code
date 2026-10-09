"""
Worker tests use an injectable async _completion to avoid real LLM calls.
process_unit now makes two calls for spec units (classify+test, then code).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from latex_ia.models import Profile, Role, Unit
from latex_ia.worker import _extract_json, _test_calls_function, process_unit


def _resp_test(
    role: str = "spec",
    test_stub: str = "def test_f():\n    assert f(1) == pytest.approx(1.0)",
    **extra,
):
    """Mock response for pass 1 (classify + test generation)."""
    payload = {
        "role": role,
        "confidence": 0.9,
        "reasoning": "test reasoning",
        "test_stub": test_stub,
        "open_questions": [],
        **extra,
    }
    msg = SimpleNamespace(content=json.dumps(payload))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _resp_code(code: str = "def f(): pass  # spec: test"):
    """Mock response for pass 2 (code implementation)."""
    payload = {"code_stub": code}
    msg = SimpleNamespace(content=json.dumps(payload))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _unit(id_: str = "algorithm") -> Unit:
    return Unit(id=id_, hash="abc", raw="\\begin{algorithm}\\end{algorithm}")


def _profile() -> Profile:
    return Profile(field="machine-learning", model="gpt-4o-mini")


class TestTestCallsFunction:
    def test_valid_test_passes(self):
        stub = "def test_f():\n    expected = 1.0\n    assert f(1) == expected"
        assert _test_calls_function(stub) is True

    def test_no_assert_fails(self):
        stub = "def test_f():\n    result = f(1)"
        assert _test_calls_function(stub) is False

    def test_only_helper_calls_fails(self):
        """assert expected == pytest.approx(x) — no call to the function under test."""
        stub = "def test_f():\n    expected = 1.0\n    assert expected == pytest.approx(1.0)"
        assert _test_calls_function(stub) is False

    def test_commented_out_assert_fails(self):
        """comment-only body is a SyntaxError → treated as invalid."""
        stub = "def test_f():\n    # assert f(1) == expected"
        assert _test_calls_function(stub) is False

    def test_empty_stub_passes(self):
        assert _test_calls_function("") is True

    def test_syntax_error_fails(self):
        assert _test_calls_function("def broken(") is False


class TestExtractJson:
    def test_plain_json(self):
        data = _extract_json('{"role": "spec", "confidence": 0.9}')
        assert data["role"] == "spec"

    def test_strips_markdown_fences(self):
        data = _extract_json('```json\n{"role": "spec"}\n```')
        assert data["role"] == "spec"

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError):
            _extract_json("no json here")


class TestProcessUnit:
    def test_spec_makes_two_calls(self):
        """A spec unit triggers classify+test (pass 1) then implement (pass 2)."""
        completion = AsyncMock(side_effect=[_resp_test("spec"), _resp_code()])
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert result.role == Role.spec
        assert completion.call_count == 2

    def test_non_spec_makes_one_call(self):
        """A non-spec unit only needs pass 1 — no code generation."""
        completion = AsyncMock(return_value=_resp_test("definition", test_stub=""))
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert result.role == Role.definition
        assert completion.call_count == 1

    def test_spec_with_empty_test_stub_skips_pass2(self):
        """If pass 1 produces no tests, pass 2 is skipped (nothing to implement against)."""
        completion = AsyncMock(return_value=_resp_test("spec", test_stub=""))
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert result.role == Role.spec
        assert completion.call_count == 1

    def test_code_stub_comes_from_pass2(self):
        """The code_stub in the result is produced by the second pass."""
        code = "def scaled_dot_product_attention(Q, K, V, d_k): ..."
        completion = AsyncMock(side_effect=[_resp_test("spec"), _resp_code(code)])
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert result.code_stub == code

    def test_passes_model_to_both_calls(self):
        """The profile model is forwarded to both completion calls."""
        completion = AsyncMock(side_effect=[_resp_test("spec"), _resp_code()])
        asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        for call in completion.call_args_list:
            assert call.kwargs["model"] == "gpt-4o-mini"

    def test_bad_role_falls_back_to_unknown(self):
        """An unrecognised role string defaults to unknown with zero confidence."""
        completion = AsyncMock(return_value=_resp_test(role="not_a_role", test_stub=""))
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert result.role == Role.unknown
        assert result.confidence == 0.0

    def test_invalid_test_stub_triggers_fix_pass(self):
        """A test that only calls pytest.approx (not the function) triggers a fix pass."""
        bad_stub = "def test_f():\n    expected = 1.0\n    assert expected == pytest.approx(1.0)"
        good_stub = "def test_f():\n    assert f(1) == pytest.approx(1.0)"
        completion = AsyncMock(
            side_effect=[
                _resp_test("spec", test_stub=bad_stub),
                _resp_test("spec", test_stub=good_stub),  # fix response
                _resp_code(),  # pass 2
            ]
        )
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert completion.call_count == 3
        assert result.test_stub == good_stub

    def test_open_questions_propagated(self):
        """open_questions from pass 1 are preserved in the final UnitResult."""
        completion = AsyncMock(
            side_effect=[
                _resp_test("spec", open_questions=["What is lambda?"]),
                _resp_code(),
            ]
        )
        result = asyncio.run(process_unit(_unit(), [_unit()], _profile(), _completion=completion))
        assert "What is lambda?" in result.open_questions
