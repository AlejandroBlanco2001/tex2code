"""Resolve a .tex file tree into a single source string by inlining \\input/\\include."""

from __future__ import annotations

import re
from pathlib import Path

from latex_ia.parser.result import ParseResult

_MAX_INPUT_DEPTH = 10  # guard against circular \\input chains
_RE_INPUT = re.compile(r"\\(?:input|include)\{([^}]+)\}")


def resolve_source(path: Path, result: ParseResult, depth: int = 0) -> str:
    """
    Read *path* and inline all \\input/\\include references recursively.

    Returns the fully inlined source string.  Missing or unreadable files
    are skipped with a warning rather than raising.
    """
    if depth > _MAX_INPUT_DEPTH:
        result.warn(f"\\input depth exceeded at {path} — skipping further includes")
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        result.warn(f"could not read {path}: {exc}")
        return ""

    def _replace(m: re.Match) -> str:
        return _inline_input(m, path, result, depth)

    return _RE_INPUT.sub(_replace, text)


def _inline_input(m: re.Match, parent: Path, result: ParseResult, depth: int) -> str:
    """Resolve a single \\input match and return the inlined source."""
    target = Path(parent.parent, m.group(1))
    if not target.suffix:
        target = target.with_suffix(".tex")
    if not target.exists():
        result.warn(f"\\input file not found: {target}")
        return ""
    if depth + 1 > _MAX_INPUT_DEPTH:
        result.warn(f"\\input depth exceeded — skipping {target}")
        return ""
    return resolve_source(target, result, depth + 1)
