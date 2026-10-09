"""Tests for notebook.py — generate_notebook and write_notebook."""

from __future__ import annotations

from latex_ia.models import Manifest, ManifestEntry, Role, Unit
from latex_ia.notebook import _code_cell, _md_cell, generate_notebook, write_notebook


def _unit(uid: str, raw: str = "some latex", section: list[str] | None = None) -> Unit:
    return Unit(id=uid, hash="abc", raw=raw, section_path=section or [])


def _entry(
    role: Role = Role.spec, code: list[str] | None = None, tests: list[str] | None = None
) -> ManifestEntry:
    return ManifestEntry(
        hash="abc",
        role=role,
        last_processed="2026-01-01",
        code=code or [],
        tests=tests or [],
    )


def _manifest(entries: dict) -> Manifest:
    return Manifest(entries=entries)


def test_notebook_has_title_cell():
    nb = generate_notebook([], _manifest({}), title="MyPaper")
    assert nb["cells"][0]["cell_type"] == "markdown"
    assert "MyPaper" in nb["cells"][0]["source"]


def test_notebook_format_fields():
    nb = generate_notebook([], _manifest({}))
    assert nb["nbformat"] == 4
    assert nb["nbformat_minor"] == 5
    assert "kernelspec" in nb["metadata"]


def test_unit_becomes_markdown_cell():
    units = [_unit("u1", raw=r"\alpha = 1")]
    nb = generate_notebook(units, _manifest({}))
    sources = [c["source"] for c in nb["cells"] if c["cell_type"] == "markdown"]
    assert any("u1" in s for s in sources)
    assert any(r"\alpha = 1" in s for s in sources)


def test_code_cell_added_when_file_exists(tmp_path):
    code_file = tmp_path / "impl.py"
    code_file.write_text("x = 1\n", encoding="utf-8")
    units = [_unit("u1")]
    entry = _entry(code=[str(code_file)])
    nb = generate_notebook(units, _manifest({"u1": entry}))
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) == 1
    assert "x = 1" in code_cells[0]["source"]


def test_missing_code_file_skipped_gracefully(tmp_path):
    units = [_unit("u1")]
    entry = _entry(code=[str(tmp_path / "nonexistent.py")])
    nb = generate_notebook(units, _manifest({"u1": entry}))
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) == 0


def test_test_cell_added(tmp_path):
    test_file = tmp_path / "test_u1.py"
    test_file.write_text("def test_x(): pass\n", encoding="utf-8")
    units = [_unit("u1")]
    entry = _entry(tests=[str(test_file)])
    nb = generate_notebook(units, _manifest({"u1": entry}))
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert any("test_x" in c["source"] for c in code_cells)


def test_section_header_inserted_once():
    u1 = _unit("u1", section=["Methods"])
    u2 = _unit("u2", section=["Methods"])
    nb = generate_notebook([u1, u2], _manifest({}))
    section_cells = [
        c for c in nb["cells"] if c["cell_type"] == "markdown" and "## Methods" in c["source"]
    ]
    assert len(section_cells) == 1


def test_write_notebook_creates_ipynb(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    units = [_unit("u1")]
    path = write_notebook(units, _manifest({}), title="TestPaper")
    assert path.suffix == ".ipynb"
    assert path.exists()
    import json

    nb = json.loads(path.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    assert "TestPaper" in nb["cells"][0]["source"]


def test_md_cell_structure():
    cell = _md_cell("hello")
    assert cell["cell_type"] == "markdown"
    assert cell["source"] == "hello"


def test_code_cell_structure():
    cell = _code_cell("x = 1")
    assert cell["cell_type"] == "code"
    assert cell["outputs"] == []
    assert cell["execution_count"] is None
