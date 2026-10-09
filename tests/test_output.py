import os
from pathlib import Path

import pytest

from latex_ia.models import Manifest, ManifestEntry, Role, Unit, UnitResult
from latex_ia.output import _stem, _name_from_label, write_result


def _unit(id_: str, section_path: list[str] | None = None) -> Unit:
    return Unit(id=id_, hash="abc123", raw="content", section_path=section_path or [])


def _result(role: Role = Role.spec, code: str = "def f(): pass", test: str = "def test_f(): pass"):
    return UnitResult(role=role, confidence=0.9, reasoning="test", code_stub=code, test_stub=test)


class TestStem:
    def test_labeled_id(self):
        """A human-readable label is used directly."""
        assert _stem(_unit("impl:loss")) == "loss"

    def test_plain_label(self):
        """An ID without a prefix is used as-is."""
        assert _stem(_unit("algorithm")) == "algorithm"

    def test_hash_uses_section_path(self):
        """A hash ID falls back to the section path for a readable name."""
        unit = _unit(
            "eq:abc123def456",
            section_path=["3 Attention", "3.1 Scaled Dot-Product Attention"],
        )
        assert _stem(unit) == "scaled_dot_product_attention"

    def test_hash_without_section_path_uses_type(self):
        """A hash ID with no section path falls back to the unit type prefix."""
        assert _stem(_unit("equation:abc123def456")) == "equation"

    def test_special_chars_replaced(self):
        """Non-alphanumeric chars in labels become underscores."""
        assert _stem(_unit("fig:model-arch")) == "model_arch"

    def test_section_stop_words_filtered(self):
        """Common stop words are stripped from section-derived names."""
        unit = _unit(
            "eq:deadbeef01234567",
            section_path=["4 Results", "4.1 Results of the Model"],
        )
        name = _stem(unit)
        assert "the" not in name.split("_")
        assert "of" not in name.split("_")

    def test_label_in_raw_preferred_over_section_path(self):
        """A \\label{} inside the equation raw takes priority over section path."""
        unit = Unit(
            id="equation:deadbeef01234567",
            hash="abc",
            raw=r"\begin{equation}\label{eq:lrate} d^{-0.5} \end{equation}",
            section_path=["Training", "Optimizer"],
        )
        assert _stem(unit) == "lrate"

    def test_name_from_label_strips_prefix(self):
        assert _name_from_label(r"\label{eq:scaled_dot}") == "scaled_dot"

    def test_name_from_label_returns_none_if_absent(self):
        assert _name_from_label(r"\begin{equation} x + y \end{equation}") is None


class TestWriteResult:
    def test_spec_writes_src_and_test(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        unit = _unit("impl:loss")
        manifest = Manifest()
        written = write_result(unit, _result(Role.spec), manifest)
        assert len(written) == 2
        assert any("loss.py" in str(p) for p in written)
        assert any("test_loss.py" in str(p) for p in written)

    def test_hash_unit_uses_section_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        unit = _unit(
            "eq:abc123def456",
            section_path=["3 Attention", "3.1 Scaled Dot-Product Attention"],
        )
        written = write_result(unit, _result(Role.spec), Manifest())
        assert any("scaled_dot_product_attention.py" in str(p) for p in written)

    def test_collision_guard_renames_second_file(self, tmp_path, monkeypatch):
        """Two spec units that map to the same stem get distinct filenames."""
        monkeypatch.chdir(tmp_path)
        unit_a = _unit("equation:aabbccdd11223344", section_path=["Training", "Optimizer"])
        unit_b = _unit("equation:11223344aabbccdd", section_path=["Training", "Optimizer"])
        write_result(unit_a, _result(Role.spec), Manifest())
        written_b = write_result(unit_b, _result(Role.spec), Manifest())
        paths = [str(p) for p in written_b if "src" in str(p)]
        assert paths  # at least one src file
        assert "optimizer.py" not in paths[0]  # should be optimizer_2.py

    def test_non_spec_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        written = write_result(_unit("intro:1"), _result(Role.context, code="", test=""), Manifest())
        assert written == []

    def test_manifest_updated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manifest = Manifest()
        write_result(_unit("impl:loss"), _result(), manifest)
        assert "impl:loss" in manifest.entries
        assert manifest.entries["impl:loss"].hash == "abc123"
        assert manifest.entries["impl:loss"].role == Role.spec

    def test_open_questions_written(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = UnitResult(
            role=Role.spec, confidence=0.8, reasoning="r",
            code_stub="def f(): pass",
            open_questions=["What is lambda?"],
        )
        write_result(_unit("impl:loss"), result, Manifest())
        questions = (tmp_path / ".tex2code/questions.md").read_text()
        assert "What is lambda?" in questions
