"""
Public API for the LaTeX parser.

    parse(path)           → list[Unit]          (never raises)
    parse_document(path)  → ParseResult         (units + warnings)
"""

from __future__ import annotations

from pathlib import Path

from latex_ia.models import Unit
from latex_ia.parser.resolver import resolve_source
from latex_ia.parser.result import ParseResult
from latex_ia.parser.walker import parse_source

__all__ = ["parse", "parse_document", "ParseResult"]


def parse_document(path: Path) -> ParseResult:
    """
    Parse a .tex file tree and return a ParseResult with units and warnings.

    Never raises — partial results are returned on any error, with the
    problem recorded in ParseResult.warnings.
    """
    result = ParseResult()
    try:
        source = resolve_source(path, result)
        parse_source(source, result)
    except Exception as exc:  # noqa: BLE001
        result.warn(f"parse failed for {path}: {exc}")
    return result


def parse(path: Path) -> list[Unit]:
    """
    Parse a .tex file tree and return the list of units.

    Convenience wrapper around parse_document() for callers that do not
    need the warnings.  Never raises.
    """
    return parse_document(path).units
