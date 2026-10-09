"""
Acceptance tests for "Auto-Encoding Variational Bayes" (Kingma & Welling, 2013).
arXiv:1312.6114 — real LaTeX source with shared/commands.tex and appendix.

This paper is a good stress-test because:
  - Equations use a custom \\eqnr macro inside align* — labels not detected yet (known gap).
  - Has a concrete Algorithm environment (AEVB) that is textbook spec content.
  - Appendix is inlined via \\input — tests cross-file parsing.
"""

import pytest

from latex_ia.classifier.gate import gate
from latex_ia.classifier.rules import RuleClassifier
from latex_ia.models import Manifest, Role
from tests.integration.conftest import VAE_TEX

pytestmark = pytest.mark.integration

KNOWN_IDS = {
    "algorithm",  # AEVB algorithm — primary spec unit
    "algorithm_ap",  # appendix algorithm
    "fig:lowbound",
    "fig:marglik",
    "fig:2dmanifolds",
    "fig:mnistsamples",
    "eq:f_ap",  # equation in appendix with standard \label
}

# Known gap: align* + custom \eqnr macro — labeled equations not yet detected.
# These labels exist in the paper but the parser cannot extract them yet.
KNOWN_PARSER_GAPS = {
    "eq:lowerbound",
    "eq:lowerbound2",
    "eq:fullestimator",
    "eq:estimator2",
    "eq:gaussian_estimator",
}


class TestParserRobustness:
    def test_parses_without_error(self, vae_units):
        assert isinstance(vae_units, list)

    def test_follows_input_files(self, vae_units):
        """Appendix and shared/commands.tex are \\input — must be inlined."""
        ids = {u.id for u in vae_units}
        # algorithm_ap comes from the appendix file
        assert "algorithm_ap" in ids

    def test_total_unit_count(self, vae_units):
        assert len(vae_units) == 9

    def test_unit_ids_are_stable(self, vae_units):
        from latex_ia.parser import parse

        second = parse(VAE_TEX)
        assert [u.id for u in vae_units] == [u.id for u in second]


class TestKnownUnits:
    def test_known_ids_present(self, vae_units):
        ids = {u.id for u in vae_units}
        assert KNOWN_IDS.issubset(ids), f"Missing: {KNOWN_IDS - ids}"

    def test_algorithm_unit_present(self, vae_units):
        """AEVB algorithm is the primary implementable spec in this paper."""
        ids = {u.id for u in vae_units}
        assert "algorithm" in ids

    def test_known_parser_gaps(self, vae_units):
        """
        Labeled equations inside align* + custom \\eqnr are not yet detected.
        This test documents the gap — it should be converted to a positive
        assertion once the parser handles custom numbering macros.
        """
        ids = {u.id for u in vae_units}
        missing = KNOWN_PARSER_GAPS & ids
        assert missing == set(), f"Parser now detects these — update KNOWN_PARSER_GAPS: {missing}"

    def test_no_units_are_marked(self, vae_units):
        assert all(not u.marked for u in vae_units)


class TestGateBehavior:
    def test_all_gated_tier_minus1(self, vae_units):
        manifest = Manifest()
        for unit in vae_units:
            result = gate(unit, manifest)
            assert result is not None and result.skipped
            assert result.tier_used == -1


class TestRuleClassifier:
    def test_algorithm_would_be_spec(self, vae_units):
        """
        If the algorithm unit were marked, the rule classifier would assign spec.
        Validates that \begin{algorithm} → Role.spec rule is correct for this paper.
        """
        rule_clf = RuleClassifier()
        algo = next(u for u in vae_units if u.id == "algorithm")

        # Simulate the unit being marked so it passes the gate
        marked = algo.model_copy(update={"marked": True, "marker_type": "tcprocess"})
        result = rule_clf.classify(marked)

        assert result is not None
        assert result.role == Role.spec


class TestAnnotatedVersion:
    """
    Full pipeline tests against an annotated copy of the paper.
    Skipped until examples/vae/iclr14_sva_annotated.tex is created.
    """

    annotated = VAE_TEX.parent / "iclr14_sva_annotated.tex"

    @pytest.mark.skipif(not annotated.exists(), reason="annotated version not yet created")
    def test_aevb_algorithm_classified_as_spec(self):
        from latex_ia.parser import parse

        units = parse(self.annotated)
        rule_clf = RuleClassifier()
        algo = next((u for u in units if "algorithm" in u.id and u.marked), None)
        assert algo is not None
        result = rule_clf.classify(algo)
        assert result is not None and result.role == Role.spec
