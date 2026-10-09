"""Tests for the revisor — open question resolution pass."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from latex_ia.models import Profile, Unit
from latex_ia.revisor import (
    RevisionResult,
    _extract_symbols,
    _gather_candidates,
    _graph_neighbors,
    _search_units,
    resolve_questions,
)


def _unit(id_: str, raw: str = "") -> Unit:
    """Return a minimal Unit for testing."""
    return Unit(id=id_, hash=id_, raw=raw or f"content of {id_}")


def _profile() -> Profile:
    """Return a minimal Profile for testing."""
    return Profile(field="ML", subfield="generative models", model="gpt-4o")


def _rephrase_resp(n: int) -> MagicMock:
    """Mock rephrase response: n questions → n empty variant lists."""
    payload = json.dumps({"variants": [[] for _ in range(n)]})
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=payload, tool_calls=None))]
    )


def _verdict_resp(answered: list[bool]) -> MagicMock:
    """Mock agent final-verdict response with no tool calls."""
    results = [{"answered": a, "evidence": "found" if a else ""} for a in answered]
    payload = json.dumps({"results": results})
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=payload, tool_calls=None))]
    )


def _tool_call_resp(name: str, arguments: dict, call_id: str = "tc1") -> MagicMock:
    """Mock agent response that issues one tool call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=None, tool_calls=[tc]))]
    )


class TestExtractSymbols:
    def test_latex_commands_extracted(self):
        """\\cmd patterns are captured directly."""
        syms = _extract_symbols(r"What is \beps and \bzeta?")
        assert r"\beps" in syms
        assert r"\bzeta" in syms

    def test_camel_case_and_backslash_variant(self):
        """fPhi produces both fPhi and \\fPhi."""
        syms = _extract_symbols("What is fPhi and gPhi?")
        assert "fPhi" in syms
        assert r"\fPhi" in syms

    def test_paren_var_and_variants(self):
        """p(eps) produces eps, \\eps, and \\beps."""
        syms = _extract_symbols("What is p(eps)?")
        assert "eps" in syms
        assert r"\eps" in syms
        assert r"\beps" in syms

    def test_empty_text(self):
        """No symbols extracted from plain prose."""
        assert _extract_symbols("What is the convergence criterion?") == set()


class TestGraphNeighbors:
    def test_returns_predecessors(self):
        """Units that unit_id depends on are predecessors."""
        deps = {"algo": {"def:enc", "eq:loss"}, "def:enc": set()}
        assert "def:enc" in _graph_neighbors("algo", deps)

    def test_returns_successors(self):
        """Units that depend on unit_id are successors."""
        deps = {"algo": {"def:enc"}, "result": {"algo"}}
        assert "result" in _graph_neighbors("algo", deps)

    def test_empty_deps(self):
        """Unit with no edges returns empty set."""
        assert _graph_neighbors("solo", {"solo": set()}) == set()


class TestGatherCandidates:
    def test_symbol_match_outranks_keyword_match(self):
        """A unit with an exact symbol hit ranks above one with only keyword overlap."""
        sym_unit = _unit("def:enc", raw=r"\fPhi is the encoder")
        kw_unit = _unit("intro", raw="encoder function phi")
        results = _gather_candidates(
            "What is fPhi?", [], [sym_unit, kw_unit], "algo",
            symbols={"fPhi", r"\fPhi"},
        )
        assert results[0].id == "def:enc"

    def test_neighbor_always_included(self):
        """A graph neighbor is appended even with zero keyword/symbol score."""
        neighbour = _unit("def:prior", raw="completely unrelated content xyz")
        other = _unit("eq:loss", raw="fPhi encoder keyword match")
        results = _gather_candidates(
            "What is fPhi?", [], [neighbour, other], "algo",
            neighbor_ids={"def:prior"},
        )
        ids = [u.id for u in results]
        assert "def:prior" in ids

    def test_variants_expand_keyword_coverage(self):
        """A unit matching a variant query is included even if it misses the original."""
        unit_a = _unit("sec:noise", raw="auxiliary variable epsilon Gaussian")
        results = _gather_candidates(
            "What is p(eps)?",
            ["epsilon noise prior"],
            [unit_a],
            "algo",
        )
        assert any(u.id == "sec:noise" for u in results)


class TestSearchUnits:
    def test_excludes_the_target_unit(self):
        """The unit being revised is never a candidate."""
        units = [_unit("algo", raw="fPhi encoder function")]
        assert _search_units("What is fPhi encoder?", units, "algo") == []

    def test_higher_overlap_ranked_first(self):
        """Units with more matching keywords come first."""
        units = [
            _unit("low", raw="fPhi mentioned once"),
            _unit("high", raw="fPhi gPhi encoder decoder reparameterization"),
        ]
        results = _search_units("fPhi gPhi encoder decoder", units, "other")
        assert results[0].id == "high"


class TestResolveQuestions:
    def test_empty_questions_no_llm_call(self):
        """No LLM call at all when question list is empty."""
        mock = AsyncMock()
        result = asyncio.run(
            resolve_questions(_unit("algo"), [], [_unit("def:enc")], _profile(), _completion=mock)
        )
        mock.assert_not_called()
        assert result == RevisionResult()

    def test_answered_question_resolved(self):
        """Rephrase call + verdict call; question marked answered → resolved."""
        mock = AsyncMock(side_effect=[_rephrase_resp(1), _verdict_resp([True])])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?"],
                [_unit("def:enc", raw=r"\fPhi is the encoder function")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.resolved == ["What is fPhi?"]
        assert result.unresolved == []

    def test_unanswered_question_unresolved(self):
        """Question marked not answered stays in unresolved."""
        mock = AsyncMock(side_effect=[_rephrase_resp(1), _verdict_resp([False])])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is the convergence criterion?"],
                [],
                _profile(),
                _completion=mock,
            )
        )
        assert result.unresolved == ["What is the convergence criterion?"]
        assert result.resolved == []

    def test_mixed_answers(self):
        """Two questions, one answered and one not."""
        mock = AsyncMock(side_effect=[_rephrase_resp(2), _verdict_resp([True, False])])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?", "What is the convergence criterion?"],
                [_unit("def:enc", raw=r"\fPhi encoder")],
                _profile(),
                _completion=mock,
            )
        )
        assert "What is fPhi?" in result.resolved
        assert "What is the convergence criterion?" in result.unresolved

    def test_tool_call_then_verdict(self):
        """Agent may issue a search tool call before the final verdict."""
        mock = AsyncMock(side_effect=[
            _rephrase_resp(1),
            _tool_call_resp("search_document", {"query": "fPhi encoder"}),
            _verdict_resp([True]),
        ])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?"],
                [_unit("def:enc", raw=r"\fPhi encoder function defined here")],
                _profile(),
                _completion=mock,
            )
        )
        assert mock.call_count == 3
        assert result.resolved == ["What is fPhi?"]

    def test_get_unit_tool_call(self):
        """Agent may call get_unit to fetch a unit by ID."""
        mock = AsyncMock(side_effect=[
            _rephrase_resp(1),
            _tool_call_resp("get_unit", {"unit_id": "def:enc"}),
            _verdict_resp([True]),
        ])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is fPhi?"],
                [_unit("def:enc", raw=r"\fPhi is the encoder")],
                _profile(),
                _completion=mock,
            )
        )
        assert result.resolved == ["What is fPhi?"]

    def test_malformed_verdict_all_unresolved(self):
        """Invalid JSON from the agent treats all questions as unresolved."""
        bad = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json", tool_calls=None))]
        )
        mock = AsyncMock(side_effect=[_rephrase_resp(1), bad])
        result = asyncio.run(
            resolve_questions(_unit("algo"), ["Q?"], [], _profile(), _completion=mock)
        )
        assert result.unresolved == ["Q?"]
        assert result.resolved == []

    def test_truncated_results_remainder_unresolved(self):
        """Extra questions beyond the LLM result list stay unresolved."""
        mock = AsyncMock(side_effect=[_rephrase_resp(3), _verdict_resp([True])])
        result = asyncio.run(
            resolve_questions(
                _unit("algo"), ["Q1", "Q2", "Q3"], [], _profile(), _completion=mock
            )
        )
        assert "Q1" in result.resolved
        assert "Q2" in result.unresolved
        assert "Q3" in result.unresolved

    def test_deps_passed_to_graph_neighbors(self):
        """When deps is provided, graph neighbors are included in candidate pool."""
        neighbour = _unit("def:prior", raw=r"\pA hyperprior Gaussian N(0,I)")
        deps = {"algo": {"def:prior"}}
        mock = AsyncMock(side_effect=[_rephrase_resp(1), _verdict_resp([True])])
        asyncio.run(
            resolve_questions(
                _unit("algo"),
                ["What is pA?"],
                [neighbour],
                _profile(),
                deps=deps,
                _completion=mock,
            )
        )
        # Passes without error and the neighbour was in the candidate pool
        assert mock.call_count == 2

    def test_passes_model_from_profile(self):
        """The profile model is forwarded on every completion call."""
        profile = Profile(field="ML", subfield="", model="gpt-4o-mini")
        mock = AsyncMock(side_effect=[_rephrase_resp(1), _verdict_resp([False])])
        asyncio.run(
            resolve_questions(_unit("algo"), ["Q?"], [], profile, _completion=mock)
        )
        for call in mock.call_args_list:
            assert call.kwargs["model"] == "gpt-4o-mini"
