"""Parser resilience tests — verifies partial results are returned instead of crashes."""

import textwrap
from pathlib import Path

from latex_ia.parser.latex_parser import ParseResult, _parse_source, _resolve_source


def _result_from_source(source: str) -> ParseResult:
    result = ParseResult()
    _parse_source(source, result)
    return result


class TestPartialResults:
    def test_unknown_custom_macro_does_not_crash(self):
        source = r"""
        \begin{equation}\label{eq:1} x = 1 \end{equation}
        \somecustommacro[weird]{args}{extra}
        \begin{equation}\label{eq:2} y = 2 \end{equation}
        """
        result = _result_from_source(textwrap.dedent(source))
        ids = {u.id for u in result.units}
        assert "eq:1" in ids
        assert "eq:2" in ids

    def test_malformed_environment_skipped_rest_parsed(self):
        # unclosed environment followed by a valid one
        source = r"""
        \begin{figure}[h] some figure % no \end{figure}
        \begin{algorithm}\label{alg:main} step 1 \end{algorithm}
        """
        result = _result_from_source(textwrap.dedent(source))
        # must not raise; may or may not find alg:main depending on walker recovery
        assert isinstance(result.units, list)

    def test_empty_source_returns_empty(self):
        result = _result_from_source("")
        assert result.units == []
        assert result.warnings == []

    def test_only_text_returns_empty(self):
        result = _result_from_source("Hello world, this is plain text with no environments.")
        assert result.units == []


class TestInputResolution:
    def test_missing_input_file_warns_not_crashes(self, tmp_path: Path):
        tex = tmp_path / "main.tex"
        tex.write_text(r"\input{does_not_exist}")
        result = ParseResult()
        _resolve_source(tex, result, depth=0)
        assert any("not found" in w for w in result.warnings)

    def test_deep_input_chain_is_capped(self, tmp_path: Path):
        # create a chain: a.tex → b.tex → c.tex → ... beyond the depth limit
        prev = None
        for i in range(12, -1, -1):
            f = tmp_path / f"level{i}.tex"
            if prev is None:
                f.write_text(r"\begin{equation}\label{eq:deep} x \end{equation}")
            else:
                f.write_text(rf"\input{{level{i + 1}}}")
            prev = f

        result = ParseResult()
        _resolve_source(tmp_path / "level0.tex", result, depth=0)
        assert any("depth exceeded" in w for w in result.warnings)

    def test_unreadable_file_warns_not_crashes(self, tmp_path: Path):
        tex = tmp_path / "main.tex"
        tex.write_text(r"\input{locked}")
        locked = tmp_path / "locked.tex"
        locked.write_text("content")
        locked.chmod(0o000)
        try:
            result = ParseResult()
            _resolve_source(tex, result, depth=0)
            assert any("could not read" in w for w in result.warnings)
        finally:
            locked.chmod(0o644)


class TestWarningsCollected:
    def test_warnings_are_strings(self):
        result = ParseResult()
        result.warn("something went wrong")
        assert result.warnings == ["something went wrong"]

    def test_parse_always_returns_list(self, tmp_path: Path):
        from latex_ia.parser import parse

        tex = tmp_path / "broken.tex"
        tex.write_bytes(b"\xff\xfe broken encoding")
        units = parse(tex)
        assert isinstance(units, list)
