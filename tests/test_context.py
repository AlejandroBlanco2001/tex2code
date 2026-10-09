from latex_ia.context import build_context
from latex_ia.models import Unit


def _unit(id_: str, raw: str = "", section: list[str] | None = None) -> Unit:
    return Unit(id=id_, hash=id_, raw=raw, section_path=section or [])


def test_returns_target_raw_when_only_unit():
    u = _unit("algo", raw="\\begin{algorithm}")
    assert "algo" in build_context(u, [u])


def test_target_marker_present():
    units = [_unit(f"u{i}", raw=f"content {i}") for i in range(5)]
    ctx = build_context(units[2], units)
    assert "← TARGET" in ctx


def test_window_limits_neighbours():
    units = [_unit(f"u{i}", raw=f"content {i}") for i in range(20)]
    ctx = build_context(units[10], units)
    # Only units 7-13 should appear (window=3 each side)
    assert "u6" not in ctx
    assert "u7" in ctx
    assert "u13" in ctx
    assert "u14" not in ctx


def test_unknown_unit_returns_raw():
    units = [_unit("a"), _unit("b")]
    orphan = _unit("orphan", raw="orphan content")
    result = build_context(orphan, units)
    assert result == "orphan content"


def test_section_path_in_output():
    u = _unit("eq:1", section=["Method", "Training"])
    ctx = build_context(u, [u])
    assert "Method > Training" in ctx
