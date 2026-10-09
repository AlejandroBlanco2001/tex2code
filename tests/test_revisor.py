"""Tests for the revisor — open question resolution pass."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from latex_ia.models import Profile, Unit
from latex_ia.revisor import RevisionResult, _search_units, resolve_questions


def _unit(id_: str, raw: str = "") -> Unit:
    """Return a minimal Unit for testing."""
    return Unit(id=id_, hash=id_, raw=raw or f"content of {id_}")


def _profile() -> Profile:
    """Return a minimal Profile for testing."""
    return Profile(field="ML", subfield="generative models", model="gpt-4o")


def _mock_completion(answered: list[bool]) -> AsyncMock:
    """Build an AsyncMock that returns a revisor response for each question."""
    results = [
        {"answered": a, "evidence": "found in passage" if a else ""}
        for a in answered
    ]
    payload = json.dumps({"results": results})
    mock = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content=payload))]
        )
    )
    return mock


class TestSearchUnits:
    def test_returns_units_with_matching_words(self):
        """Units whose raw text contains question keywords are returned."""
        units = [
            _unit("def:enc", raw="the encoder function fPhi maps inputs to latent space"),
            _unit("intro", raw="we propose a variational autoencoder"),
        ]
        results = _search_units("What is the encoder function fPhi?", units, "algo")
        ids = [u.id for u in results]
        assert "def:enc" in ids

    def test_excludes_the_target_unit(self):
        """The unit being revised is never included in its own candidates."""
        units = [_unit("algo", raw="the encoder function fPhi is defined here")]
        results = _search_units("What is fPhi encoder function?", units, "algo")
        assert results == []

    def test_returns_empty_when_no_overlap(self):
        """No candidates when question words are absent from all units."""
        units = [_unit("intro", raw="general introduction")]
        results = _search_units("What is fPhi zeta reparameterization?", units, "algo")
        assert results == []

    def test_respects_max_candidates_cap(self):
        """At most _MAX_CANDIDATES units are returned."""
        units = [_unit(f"u{i}", raw="fPhi gPhi encoder") for i in range(20)]
        results = _search_units("What is fPhi gPhi encoder?", units, "other")
        assert len(results) <= 5

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
        assert result.resolved == []
        assert result.unresolved == []

    def test_answered_question_goes_to_resolved(self):
        """A question the LLM marks answered is placed in resolved."""
        questions = ["What is fPhi?"]
        mock = _mock_completion([True])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                questions,
                [_unit("def:enc", raw="fPhi is the encoder function")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.resolved == ["What is fPhi?"]
        assert result.unresolved == []

    def test_unanswered_question_goes_to_unresolved(self):
        """A question the LLM marks not answered is placed in unresolved."""
        questions = ["What is the convergence criterion?"]
        mock = _mock_completion([False])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                questions,
                [_unit("related", raw="we compare against baselines")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.unresolved == ["What is the convergence criterion?"]
        assert result.resolved == []

    def test_mixed_answers_split_correctly(self):
        """Answered and unanswered questions end up in their respective lists."""
        questions = ["What is fPhi?", "What is the convergence criterion?"]
        mock = _mock_completion([True, False])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                questions,
                [_unit("def:enc", raw="fPhi encoder")],
                _profile(),
                _completion=mock,
            )
        )
        assert "What is fPhi?" in result.resolved
        assert "What is the convergence criterion?" in result.unresolved

    def test_malformed_llm_response_treats_all_as_unresolved(self):
        """If LLM returns invalid JSON, all questions stay unresolved (safe fallback)."""
        questions = ["What is fPhi?"]
        mock = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="not json at all"))]
            )
        )
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                questions,
                [],
                _profile(),
                _completion=mock,
            )
        )
        assert result.unresolved == questions
        assert result.resolved == []

    def test_truncated_results_remainder_treated_as_unresolved(self):
        """If LLM returns fewer results than questions, extras stay unresolved."""
        questions = ["Q1", "Q2", "Q3"]
        mock = _mock_completion([True])  # only one result
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                questions,
                [],
                _profile(),
                _completion=mock,
            )
        )
        assert "Q1" in result.resolved
        assert "Q2" in result.unresolved
        assert "Q3" in result.unresolved

    def test_passes_model_from_profile(self):
        """The profile's model is forwarded to the completion call."""
        profile = Profile(field="ML", subfield="", model="gpt-4o-mini")
        mock = _mock_completion([False])
        asyncio.run(
            resolve_questions(_unit("algo"), ["Q?"], [], profile, _completion=mock)
        )
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
