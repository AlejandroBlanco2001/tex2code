import os
from pathlib import Path

import pytest

from latex_ia.models import Manifest, Role, Unit, UnitResult
from latex_ia.output import _stem, write_result


def _unit(id_: str) -> Unit:
    return Unit(id=id_, hash="abc123", raw="content")


def _result(role: Role = Role.spec, code: str = "def f(): pass", test: str = "def test_f(): pass"):
    return UnitResult(
        role=role,
        confidence=0.9,
        reasoning="test",
        code_stub=code,
        test_stub=test,
    )


class TestStem:
    def test_impl_prefix(self):
        assert _stem("impl:loss") == "loss"

    def test_plain_label(self):
        assert _stem("algorithm") == "algorithm"

    def test_hash_id(self):
        assert _stem("eq:abc123def") == "abc123def"

    def test_special_chars_replaced(self):
        assert _stem("fig:model-arch") == "model_arch"


class TestWriteResult:
    def test_spec_writes_src_and_test(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        unit = _unit("impl:loss")
        manifest = Manifest()
        written = write_result(unit, _result(Role.spec), manifest)
        assert len(written) == 2
        assert any("loss.py" in str(p) for p in written)
        assert any("test_loss.py" in str(p) for p in written)

    def test_non_spec_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _result(Role.context, code="", test="")
        written = write_result(_unit("intro:1"), result, Manifest())
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
            role=Role.spec,
            confidence=0.8,
            reasoning="r",
            code_stub="def f(): pass",
            open_questions=["What is lambda?"],
        )
        write_result(_unit("impl:loss"), result, Manifest())
        questions = (tmp_path / ".tex2code/questions.md").read_text()
        assert "What is lambda?" in questions
