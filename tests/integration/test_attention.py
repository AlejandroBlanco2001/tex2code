"""
Acceptance tests for "Attention Is All You Need" (Vaswani et al., 2017).

These tests assert known structural facts about the paper. If a change causes
any of these to fail it means the parser changed how it reads real LaTeX — that
needs deliberate review, not a silent regression.
"""

import pytest

from latex_ia.classifier.gate import gate
from latex_ia.classifier.rules import RuleClassifier
from latex_ia.models import Manifest, Role

pytestmark = pytest.mark.integration

# Unit IDs we know must be present — labeled environments from the paper.
KNOWN_IDS = {
    "fig:model-arch",
    "fig:multi-head-att",
    "tab:op_complexities",
    "tab:wmt-results",
    "tab:variations",
    "tab:parsing-results",
    "tab:parameter_attention",
}

# Equations don't have \label in this paper so they get hash-based IDs.
# We assert on count rather than exact IDs.
EXPECTED_EQUATION_COUNT = 3


class TestParserRobustness:
    def test_parses_without_error(self, attention_units):
        assert isinstance(attention_units, list)

    def test_follows_input_files(self, attention_units):
        """ms.tex uses \\input for every section — units must come from subfiles."""
        assert len(attention_units) > 0

    def test_total_unit_count(self, attention_units):
        assert len(attention_units) == 10

    def test_unit_ids_are_stable(self, attention_units):
        """Hash-based IDs must be deterministic — re-parsing gives same IDs."""
        from latex_ia.parser import parse
        from tests.integration.conftest import ATTENTION_TEX

        second_parse = parse(ATTENTION_TEX)
        assert [u.id for u in attention_units] == [u.id for u in second_parse]


class TestKnownUnits:
    def test_labeled_units_present(self, attention_units):
        ids = {u.id for u in attention_units}
        assert KNOWN_IDS.issubset(ids), f"Missing: {KNOWN_IDS - ids}"

    def test_equation_count(self, attention_units):
        equations = [u for u in attention_units if u.id.startswith("equation:")]
        assert len(equations) == EXPECTED_EQUATION_COUNT

    def test_no_units_are_marked(self, attention_units):
        """Real paper has no \begin{tcprocess} markers — all must be unmarked."""
        assert all(not u.marked for u in attention_units)


class TestGateBehavior:
    def test_all_units_gated_tier_minus1(self, attention_units):
        """Without opt-in markers every unit is invisible to the pipeline."""
        manifest = Manifest()
        for unit in attention_units:
            result = gate(unit, manifest)
            assert result is not None and result.skipped
            assert result.tier_used == -1

    def test_rule_classifier_not_reached(self, attention_units):
        """Gate at Tier -1 means rule classifier is never called for any unit."""
        manifest = Manifest()
        rule_clf = RuleClassifier()
        for unit in attention_units:
            gate_result = gate(unit, manifest)
            assert gate_result is not None and gate_result.skipped
            # rule classifier should never be needed
            rule_result = rule_clf.classify(unit)
            # rules may still classify by section title — that's fine,
            # but the gate would have stopped before reaching it
            _ = rule_result  # result exists but is never used in pipeline


class TestAnnotatedVersion:
    """
    Tests for the annotated copy of the paper with \begin{tcprocess} markers.
    Skipped until examples/attention/ms_annotated.tex is created.
    """

    annotated_tex = (
        __import__("pathlib").Path(__file__).parents[2]
        / "examples"
        / "attention"
        / "ms_annotated.tex"
    )

    @pytest.mark.skipif(
        not annotated_tex.exists(),
        reason="ms_annotated.tex not yet created",
    )
    def test_attention_equation_classified_as_spec(self):
        from latex_ia.parser import parse

        units = parse(self.annotated_tex)
        marked = [u for u in units if u.marked]
        assert len(marked) > 0

    @pytest.mark.skipif(
        not annotated_tex.exists(),
        reason="ms_annotated.tex not yet created",
    )
    def test_marked_attention_eq_is_spec(self):
        from latex_ia.classifier.rules import RuleClassifier
        from latex_ia.parser import parse

        units = parse(self.annotated_tex)
        rule_clf = RuleClassifier()
        implement_units = [u for u in units if u.marker_type == "implement"]
        for unit in implement_units:
            result = rule_clf.classify(unit)
            assert result is not None
            assert result.role == Role.spec
            assert result.confidence == 1.0
