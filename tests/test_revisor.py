"""Tests for the revisor — open question resolution pass."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from latex_ia.models import Profile, Unit
from latex_ia.revisor import RevisionResult, _search_units, resolve_questions


def _unit(id_: str, raw: str = "") -> Unit:
    """Return a minimal Unit for testing."""
    return Unit(id=id_, hash=id_, raw=raw or f"content of {id_}")


def _profile() -> Profile:
    """Return a minimal Profile for testing."""
    return Profile(field="ML", subfield="generative models", model="gpt-4o")


def _direct_response(answered: list[bool]) -> MagicMock:
    """Build a mock completion response that returns a JSON verdict with no tool calls."""
    results = [
        {"answered": a, "evidence": "found in passage" if a else ""}
        for a in answered
    ]
    payload = json.dumps({"results": results})
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=payload, tool_calls=None))]
    )


def _tool_call_response(name: str, arguments: dict, call_id: str = "tc1") -> MagicMock:
    """Build a mock completion response that issues one tool call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=None, tool_calls=[tc]))]
    )


class TestSearchUnits:
    def test_returns_units_with_matching_words(self):
        """Units whose raw text contains question keywords are returned."""
        units = [
            _unit("def:enc", raw="the encoder function fPhi maps inputs to latent space"),
            _unit("intro", raw="general introduction text"),
        ]
        results = _search_units("What is the encoder function fPhi?", units, "algo")
        assert any(u.id == "def:enc" for u in results)

    def test_excludes_the_target_unit(self):
        """The unit being revised is never included in its own candidates."""
        units = [_unit("algo", raw="the encoder function fPhi is defined here")]
        assert _search_units("What is fPhi encoder function?", units, "algo") == []

    def test_returns_empty_when_no_overlap(self):
        """No candidates when question words are absent from all units."""
        units = [_unit("intro", raw="general introduction")]
        assert _search_units("What is fPhi zeta reparameterization?", units, "algo") == []

    def test_respects_max_candidates_cap(self):
        """At most _MAX_CANDIDATES units are returned."""
        units = [_unit(f"u{i}", raw="fPhi gPhi encoder") for i in range(20)]
        results = _search_units("What is fPhi gPhi encoder?", units, "other")
        assert len(results) <= 6

    def test_higher_overlap_ranked_first(self):
        """Units with more keyword matches come before units with fewer."""
        units = [
            _unit("low", raw="fPhi is mentioned once"),
            _unit("high", raw="fPhi gPhi encoder decoder reparameterization"),
        ]
        results = _search_units("What is fPhi gPhi encoder decoder?", units, "algo")
        assert results[0].id == "high"


class TestResolveQuestions:
    def test_empty_questions_returns_immediately(self):
        """No LLM call when there are no open questions."""
        mock = AsyncMock()
        result = asyncio.run(
            resolve_questions(_unit("algo"), [], [_unit("def:enc")], _profile(), _completion=mock)
        )
        mock.assert_not_called()
        assert result == RevisionResult()

    def test_answered_question_goes_to_resolved(self):
        """A question the LLM marks answered is placed in resolved."""
        mock = AsyncMock(return_value=_direct_response([True]))
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?"],
                [_unit("def:enc", raw="fPhi is the encoder function")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.resolved == ["What is fPhi?"]
        assert result.unresolved == []

    def test_unanswered_question_goes_to_unresolved(self):
        """A question the LLM marks not answered is placed in unresolved."""
        mock = AsyncMock(return_value=_direct_response([False]))
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is the convergence criterion?"],
                [_unit("related", raw="we compare against baselines")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.unresolved == ["What is the convergence criterion?"]
        assert result.resolved == []

    def test_mixed_answers_split_correctly(self):
        """Answered and unanswered questions end up in their respective lists."""
        mock = AsyncMock(return_value=_direct_response([True, False]))
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?", "What is the convergence criterion?"],
                [_unit("def:enc", raw="fPhi encoder")],
                _profile(),
                _completion=mock,
            )
        )
        assert "What is fPhi?" in result.resolved
        assert "What is the convergence criterion?" in result.unresolved

    def test_tool_call_then_final_answer(self):
        """LLM can make a search tool call before giving the final verdict."""
        search_response = _tool_call_response("search_document", {"query": "fPhi encoder"})
        final_response = _direct_response([True])
        mock = AsyncMock(side_effect=[search_response, final_response])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?"],
                [_unit("def:enc", raw="fPhi is the encoder function defined here")],
                _profile(),
                _completion=mock,
            )
        )
        assert mock.call_count == 2
        assert result.resolved == ["What is fPhi?"]

    def test_get_unit_tool_call(self):
        """LLM can call get_unit to fetch a specific unit by ID."""
        lookup_response = _tool_call_response("get_unit", {"unit_id": "def:enc"})
        final_response = _direct_response([True])
        mock = AsyncMock(side_effect=[lookup_response, final_response])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?"],
                [_unit("def:enc", raw="fPhi is the encoder")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.resolved == ["What is fPhi?"]

    def test_malformed_llm_response_treats_all_as_unresolved(self):
        """If LLM returns invalid JSON, all questions stay unresolved (safe fallback)."""
        bad = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json", tool_calls=None))]
        )
        mock = AsyncMock(return_value=bad)
        result = asyncio.run(
            resolve_questions(_unit("algo"), ["Q?"], [], _profile(), _completion=mock)
        )
        assert result.unresolved == ["Q?"]
        assert result.resolved == []

    def test_truncated_results_remainder_treated_as_unresolved(self):
        """If LLM returns fewer results than questions, extras stay unresolved."""
        mock = AsyncMock(return_value=_direct_response([True]))  # only one result for 3 questions
        result = asyncio.run(
            resolve_questions(
                _unit("algo"), ["Q1", "Q2", "Q3"], [], _profile(), _completion=mock
            )
        )
        assert "Q1" in result.resolved
        assert "Q2" in result.unresolved
        assert "Q3" in result.unresolved

    def test_passes_model_from_profile(self):
        """The profile's model is forwarded to the completion call."""
        profile = Profile(field="ML", subfield="", model="gpt-4o-mini")
        mock = AsyncMock(return_value=_direct_response([False]))
        asyncio.run(
            resolve_questions(_unit("algo"), ["Q?"], [], profile, _completion=mock)
        )
        assert mock.call_args.kwargs["model"] == "gpt-4o-mini"
