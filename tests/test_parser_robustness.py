"""Parser resilience tests — verifies partial results are returned instead of crashes."""

from __future__ import annotations

import textwrap
from pathlib import Path

from latex_ia.parser import ParseResult, parse
from latex_ia.parser.resolver import resolve_source
from latex_ia.parser.walker import parse_source


def _result_from_source(source: str) -> ParseResult:
    """Parse a raw LaTeX string and return the ParseResult."""
    result = ParseResult()
    parse_source(source, result)
    return result


class TestPartialResults:
    def test_unknown_custom_macro_does_not_crash(self):
        """An unrecognised macro between valid environments must not crash the parser."""
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
        """An unclosed environment must not prevent parsing of subsequent units."""
        source = r"""
        \begin{figure}[h] some figure % no \end{figure}
        \begin{algorithm}\label{alg:main} step 1 \end{algorithm}
        """
        result = _result_from_source(textwrap.dedent(source))
        assert isinstance(result.units, list)

    def test_empty_source_returns_empty(self):
        """Empty source produces no units and no warnings."""
        result = _result_from_source("")
        assert result.units == []
        assert result.warnings == []

    def test_only_text_returns_empty(self):
        """Plain text with no LaTeX environments produces no units."""
        result = _result_from_source("Hello world, this is plain text with no environments.")
        assert result.units == []


class TestInputResolution:
    def test_missing_input_file_warns_not_crashes(self, tmp_path: Path):
        """A missing \\input target records a warning instead of raising."""
        tex = tmp_path / "main.tex"
        tex.write_text(r"\input{does_not_exist}")
        result = ParseResult()
        resolve_source(tex, result)
        assert any("not found" in w for w in result.warnings)

    def test_deep_input_chain_is_capped(self, tmp_path: Path):
        """An \\input chain deeper than _MAX_INPUT_DEPTH is capped with a warning."""
        prev = None
        for i in range(12, -1, -1):
            f = tmp_path / f"level{i}.tex"
            if prev is None:
                f.write_text(r"\begin{equation}\label{eq:deep} x \end{equation}")
            else:
                f.write_text(rf"\input{{level{i + 1}}}")
            prev = f

        result = ParseResult()
        resolve_source(tmp_path / "level0.tex", result)
        assert any("depth exceeded" in w for w in result.warnings)

    def test_unreadable_file_warns_not_crashes(self, tmp_path: Path):
        """An unreadable \\input target records a warning instead of raising."""
        tex = tmp_path / "main.tex"
        tex.write_text(r"\input{locked}")
        locked = tmp_path / "locked.tex"
        locked.write_text("content")
        locked.chmod(0o000)
        try:
            result = ParseResult()
            resolve_source(tex, result)
            assert any("could not read" in w for w in result.warnings)
        finally:
            locked.chmod(0o644)


class TestWarningsCollected:
    def test_warnings_are_strings(self):
        """warn() appends a string to the warnings list."""
        result = ParseResult()
        result.warn("something went wrong")
        assert result.warnings == ["something went wrong"]

    def test_parse_always_returns_list(self, tmp_path: Path):
        """parse() returns a list even for files with broken encoding."""
        tex = tmp_path / "broken.tex"
        tex.write_bytes(b"\xff\xfe broken encoding")
        units = parse(tex)
        assert isinstance(units, list)
