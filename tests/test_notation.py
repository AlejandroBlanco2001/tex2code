"""Tests for notation.py — generate_notation_guide and write_notation_guide."""

from __future__ import annotations

from latex_ia.models import Manifest, ManifestEntry, Role, Unit
from latex_ia.notation import generate_notation_guide, write_notation_guide


def _unit(uid: str, symbols: list[str], section: list[str] | None = None) -> Unit:
    return Unit(
        id=uid,
        hash="abc123",
        raw=f"unit {uid}",
        section_path=section or [],
        symbols=symbols,
    )


def _entry(role: Role = Role.spec, code: list[str] | None = None) -> ManifestEntry:
    return ManifestEntry(
        hash="abc123",
        role=role,
        last_processed="2026-01-01",
        code=code or [],
    )


def _manifest(entries: dict) -> Manifest:
    return Manifest(entries=entries)


def test_no_symbols_returns_placeholder():
    units = [_unit("u1", [])]
    guide = generate_notation_guide(units, _manifest({}))
    assert "No symbols tracked yet" in guide


def test_single_symbol_appears_in_table():
    units = [_unit("u1", [r"\alpha"], section=["Methods"])]
    guide = generate_notation_guide(units, _manifest({}))
    assert r"\alpha" in guide
    assert "u1" in guide
    assert "Methods" in guide


def test_role_and_code_file_in_row():
    units = [_unit("u1", [r"\beta"])]
    entry = _entry(role=Role.definition, code=["src/foo.py"])
    guide = generate_notation_guide(units, _manifest({"u1": entry}))
    assert "definition" in guide
    assert "foo.py" in guide


def test_duplicate_symbols_deduplicated():
    u1 = _unit("u1", [r"\gamma"])
    u2 = _unit("u2", [r"\gamma", r"\delta"])
    guide = generate_notation_guide([u1, u2], _manifest({}))
    assert guide.count(r"\gamma") == 1
    assert r"\delta" in guide


def test_symbols_sorted_per_unit():
    units = [_unit("u1", [r"\zeta", r"\alpha"])]
    guide = generate_notation_guide(units, _manifest({}))
    alpha_pos = guide.index(r"\alpha")
    zeta_pos = guide.index(r"\zeta")
    assert alpha_pos < zeta_pos


def test_no_code_shows_dash():
    units = [_unit("u1", [r"\mu"])]
    guide = generate_notation_guide(units, _manifest({"u1": _entry(code=[])}))
    assert "—" in guide


def test_section_join():
    units = [_unit("u1", [r"\eta"], section=["Results", "Convergence"])]
    guide = generate_notation_guide(units, _manifest({}))
    assert "Results › Convergence" in guide


def test_write_notation_guide_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    units = [_unit("u1", [r"\sigma"])]
    path = write_notation_guide(units, _manifest({}))
    assert path.exists()
    assert r"\sigma" in path.read_text(encoding="utf-8")
