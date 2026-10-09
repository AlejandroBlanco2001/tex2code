"""Tests for the symbol glossary."""

from __future__ import annotations

from latex_ia.glossary import Glossary
from latex_ia.models import Role, Unit


def _unit(id_: str, symbols: list[str] | None = None, raw: str = "") -> Unit:
    """Return a minimal Unit for testing."""
    return Unit(id=id_, hash=id_, raw=raw or f"raw for {id_}", symbols=symbols or [])


class TestGlossaryUpdate:
    def test_definition_role_registers_symbols(self):
        """A definition unit's long symbols are added to the glossary."""
        g = Glossary()
        unit = _unit("def:encoder", symbols=["fPhi", "gPhi", "theta"])
        g.update(unit, Role.definition)
        assert len(g) == 3  # fPhi, gPhi, theta all qualify (len >= 3)

    def test_assumption_role_registers_symbols(self):
        """An assumption unit also seeds the glossary."""
        g = Glossary()
        unit = _unit("ass:prior", symbols=["pZero", "sigma"])
        g.update(unit, Role.assumption)
        assert len(g) == 2

    def test_spec_role_ignored(self):
        """Spec units do not contribute to the glossary."""
        g = Glossary()
        g.update(_unit("algo", symbols=["fPhi"]), Role.spec)
        assert len(g) == 0

    def test_short_symbols_not_registered(self):
        """Symbols shorter than 3 chars are excluded."""
        g = Glossary()
        g.update(_unit("def:vars", symbols=["x", "z", "mu", "fPhi"]), Role.definition)
        assert len(g) == 1  # only fPhi

    def test_later_definition_overwrites(self):
        """A later definition of the same symbol replaces the earlier one."""
        g = Glossary()
        g.update(_unit("def:v1", symbols=["fPhi"], raw="first"), Role.definition)
        g.update(_unit("def:v2", symbols=["fPhi"], raw="second"), Role.definition)
        entries = g.resolve(_unit("algo", symbols=["fPhi"]))
        assert entries[0].unit_id == "def:v2"


class TestGlossaryResolve:
    def test_returns_matching_entries(self):
        """resolve() returns entries whose symbol appears in the target's symbols."""
        g = Glossary()
        g.update(_unit("def:enc", symbols=["fPhi"]), Role.definition)
        target = _unit("algo", symbols=["fPhi", "gPhi"])
        entries = g.resolve(target)
        assert len(entries) == 1
        assert entries[0].symbol == "fPhi"

    def test_excludes_self_definitions(self):
        """A unit does not receive its own symbols as resolved definitions."""
        g = Glossary()
        g.update(_unit("def:enc", symbols=["fPhi"]), Role.definition)
        entries = g.resolve(_unit("def:enc", symbols=["fPhi"]))
        assert entries == []

    def test_empty_when_no_overlap(self):
        """No entries returned when the target uses no known symbols."""
        g = Glossary()
        g.update(_unit("def:enc", symbols=["fPhi"]), Role.definition)
        assert g.resolve(_unit("algo", symbols=["theta"])) == []


class TestGlossaryFormatForPrompt:
    def test_empty_when_no_entries(self):
        """format_for_prompt returns empty string when nothing resolves."""
        g = Glossary()
        assert g.format_for_prompt(_unit("algo", symbols=["fPhi"])) == ""

    def test_contains_definition_header(self):
        """The formatted block includes a definition header and the raw LaTeX."""
        g = Glossary()
        g.update(_unit("def:enc", symbols=["fPhi"], raw="\\newcommand{\\fPhi}"), Role.definition)
        prompt = g.format_for_prompt(_unit("algo", symbols=["fPhi"]))
        assert "def:enc" in prompt
        assert "\\newcommand{\\fPhi}" in prompt

    def test_deduplicates_same_unit(self):
        """Multiple symbols from the same unit produce only one block."""
        g = Glossary()
        g.update(_unit("def:enc", symbols=["fPhi", "gPhi"], raw="encoder def"), Role.definition)
        target = _unit("algo", symbols=["fPhi", "gPhi"])
        prompt = g.format_for_prompt(target)
        assert prompt.count("encoder def") == 1
