"""Tests for the dependency graph builder and topological sort."""

from __future__ import annotations

from latex_ia.graph import build_dependency_map, topological_sort
from latex_ia.models import Role, Unit


def _unit(id_: str, refs: list[str] | None = None, symbols: list[str] | None = None) -> Unit:
    """Return a minimal Unit for testing."""
    return Unit(id=id_, hash=id_, raw="", refs=refs or [], symbols=symbols or [])


class TestBuildDependencyMap:
    def test_no_refs_no_deps(self):
        """Units with no refs have no dependencies."""
        units = [_unit("a"), _unit("b")]
        deps = build_dependency_map(units)
        assert deps["a"] == set()
        assert deps["b"] == set()

    def test_explicit_ref_creates_edge(self):
        """A unit that refs another depends on it."""
        units = [_unit("algo", refs=["eq:loss"]), _unit("eq:loss")]
        deps = build_dependency_map(units)
        assert "eq:loss" in deps["algo"]

    def test_ref_to_unknown_unit_ignored(self):
        """A ref to a unit not in the list is silently ignored."""
        units = [_unit("algo", refs=["eq:missing"])]
        deps = build_dependency_map(units)
        assert deps["algo"] == set()

    def test_self_ref_ignored(self):
        """A unit cannot depend on itself."""
        units = [_unit("algo", refs=["algo"])]
        deps = build_dependency_map(units)
        assert "algo" not in deps["algo"]

    def test_symbol_edge_from_definition_unit(self):
        """A definition unit's long symbols create edges for units that use them."""
        defn = _unit("def:encoder", symbols=["fPhi", "gPhi"])
        spec = _unit("algo", symbols=["fPhi"])
        hints = {"def:encoder": Role.definition}
        deps = build_dependency_map([defn, spec], role_hints=hints)
        assert "def:encoder" in deps["algo"]

    def test_short_symbols_ignored(self):
        """Single-letter and two-letter symbols do not create edges."""
        defn = _unit("def:vars", symbols=["x", "z", "mu"])
        spec = _unit("algo", symbols=["x", "z", "mu"])
        hints = {"def:vars": Role.definition}
        deps = build_dependency_map([defn, spec], role_hints=hints)
        assert deps["algo"] == set()

    def test_non_defining_role_no_symbol_edge(self):
        """Only definition/assumption roles seed the symbol index."""
        spec_a = _unit("algo_a", symbols=["fPhi"])
        spec_b = _unit("algo_b", symbols=["fPhi"])
        hints = {"algo_a": Role.spec}
        deps = build_dependency_map([spec_a, spec_b], role_hints=hints)
        assert deps["algo_b"] == set()


class TestTopologicalSort:
    def test_no_deps_preserves_document_order(self):
        """Units with no dependencies come out in their original order."""
        units = [_unit("a"), _unit("b"), _unit("c")]
        deps = build_dependency_map(units)
        ordered = topological_sort(units, deps)
        assert [u.id for u in ordered] == ["a", "b", "c"]

    def test_dependency_precedes_dependent(self):
        """A referenced unit must appear before the unit that references it."""
        definition = _unit("def:loss")
        algorithm = _unit("algo", refs=["def:loss"])
        units = [algorithm, definition]  # intentionally wrong order
        deps = build_dependency_map(units)
        ordered = topological_sort(units, deps)
        ids = [u.id for u in ordered]
        assert ids.index("def:loss") < ids.index("algo")

    def test_chain_a_depends_b_depends_c(self):
        """Transitive dependencies are resolved: C before B before A."""
        a = _unit("a", refs=["b"])
        b = _unit("b", refs=["c"])
        c = _unit("c")
        deps = build_dependency_map([a, b, c])
        ordered = topological_sort([a, b, c], deps)
        ids = [u.id for u in ordered]
        assert ids.index("c") < ids.index("b") < ids.index("a")

    def test_cycle_does_not_crash(self):
        """A circular dependency produces no crash; all units are returned."""
        a = _unit("a", refs=["b"])
        b = _unit("b", refs=["a"])
        deps = build_dependency_map([a, b])
        ordered = topological_sort([a, b], deps)
        assert {u.id for u in ordered} == {"a", "b"}

    def test_returns_all_units(self):
        """Every input unit appears exactly once in the output."""
        units = [_unit(str(i)) for i in range(10)]
        deps = build_dependency_map(units)
        ordered = topological_sort(units, deps)
        assert len(ordered) == 10
        assert {u.id for u in ordered} == {u.id for u in units}
