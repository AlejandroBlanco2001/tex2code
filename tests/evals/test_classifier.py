"""Classifier accuracy against the sample paper golden set.

No LLM calls — all blocks are either explicitly marked (tier 1/2) or
classified by keyword scorer (tier 3). Run with: make eval-classifier
"""

from __future__ import annotations

import pytest

from latex_ia.classifier import KeywordScorer, RuleClassifier, gate
from latex_ia.models import Manifest, ProcessMode, Role

# Ground truth: unit_id → expected role
GOLDEN: dict[str, Role] = {
    "def:graph": Role.definition,  # \begin{tcprocess} in "Notation" section
    "model:gnn": Role.spec,  # \begin{implement} → always spec
    "impl:loss": Role.spec,  # \begin{implement} → always spec
    "spec:training": Role.spec,  # \begin{tcprocess} in "Method" section
    "assump:gaussian": Role.assumption,  # \begin{tcprocess} with "we assume"
}

# Unmarked units that strict mode should gate out entirely
GATED_OUT = {"tab:results"}


def _classify(unit, manifest=None) -> Role:
    """Run the rule → keyword pipeline (no LLM) and return the role."""
    manifest = manifest or Manifest()

    g = gate(unit, manifest, mode=ProcessMode.strict)
    if g and g.skipped:
        return g.role

    r = RuleClassifier().classify(unit)
    if r:
        return r.role

    k = KeywordScorer().classify(unit)
    if k:
        return k.role

    return Role.unknown


class TestGoldenSet:
    @pytest.mark.parametrize("unit_id,expected_role", GOLDEN.items())
    def test_role(self, unit_id, expected_role, sample_unit_map):
        unit = sample_unit_map[unit_id]
        assert _classify(unit) == expected_role

    def test_all_golden_units_present(self, sample_unit_map):
        missing = [uid for uid in GOLDEN if uid not in sample_unit_map]
        assert not missing, f"golden units missing from parse: {missing}"

    def test_implement_marker_confidence_is_1(self, sample_unit_map):
        for uid in ("model:gnn", "impl:loss"):
            unit = sample_unit_map[uid]
            result = RuleClassifier().classify(unit)
            assert result is not None
            assert result.confidence == 1.0

    def test_definition_section_drives_role(self, sample_unit_map):
        unit = sample_unit_map["def:graph"]
        result = RuleClassifier().classify(unit)
        assert result is not None
        assert result.role == Role.definition

    def test_assumption_keyword_drives_role(self, sample_unit_map):
        """assump:gaussian has no env-level rule — keyword scorer must catch it."""
        unit = sample_unit_map["assump:gaussian"]
        rule_result = RuleClassifier().classify(unit)
        # Rules may or may not fire; keyword must handle it if they don't
        if rule_result is None:
            kw = KeywordScorer().classify(unit)
            assert kw is not None
            assert kw.role == Role.assumption


class TestGateStrict:
    def test_unmarked_units_are_skipped(self, sample_units):
        manifest = Manifest()
        for unit in sample_units:
            if unit.id in GATED_OUT:
                result = gate(unit, manifest, mode=ProcessMode.strict)
                assert result is not None and result.skipped

    def test_marked_units_pass_gate(self, sample_units):
        manifest = Manifest()
        for unit in sample_units:
            if unit.id in GOLDEN:
                result = gate(unit, manifest, mode=ProcessMode.strict)
                assert result is None, f"{unit.id} should pass gate but was skipped"

    def test_hash_cache_skips_unchanged(self, sample_unit_map):
        from latex_ia.models import ManifestEntry

        unit = sample_unit_map["model:gnn"]
        manifest = Manifest(
            entries={
                unit.id: ManifestEntry(
                    hash=unit.hash,
                    role=Role.spec,
                    last_processed="2026-01-01",
                )
            }
        )
        result = gate(unit, manifest)
        assert result is not None and result.skipped
        assert result.tier_used == 0
