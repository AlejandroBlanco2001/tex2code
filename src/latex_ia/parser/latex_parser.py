from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pylatexenc.latexwalker import LatexEnvironmentNode, LatexMacroNode, LatexWalker

from latex_ia.models import Unit

logger = logging.getLogger(__name__)

_SECTION_MACROS = {"section", "subsection", "subsubsection", "paragraph"}
_MARKER_ENVS = {"tcprocess", "implement"}
_KNOWN_ENVS = {
    "equation",
    "align",
    "algorithm",
    "algorithmic",
    "definition",
    "assumption",
    "theorem",
    "figure",
    "table",
}

_MAX_INPUT_DEPTH = 10  # guard against circular \input chains


@dataclass
class ParseResult:
    units: list[Unit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        logger.warning(msg)
        self.warnings.append(msg)


def parse(path: Path) -> list[Unit]:
    """Parse a .tex file and return all units. Never raises — returns partial results on error."""
    result = ParseResult()
    try:
        source = _resolve_source(path, result, depth=0)
        _parse_source(source, result)
    except Exception as exc:  # noqa: BLE001
        result.warn(f"parse failed for {path}: {exc}")
    return result.units


# ── source resolution ────────────────────────────────────────────────────────


def _resolve_source(path: Path, result: ParseResult, depth: int) -> str:
    if depth > _MAX_INPUT_DEPTH:
        result.warn(f"\\input depth exceeded at {path} — skipping further includes")
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        result.warn(f"could not read {path}: {exc}")
        return ""

    def _replace_input(m: re.Match) -> str:
        target = Path(path.parent, m.group(1))
        if not target.suffix:
            target = target.with_suffix(".tex")
        if not target.exists():
            result.warn(f"\\input file not found: {target}")
            return ""
        if depth + 1 > _MAX_INPUT_DEPTH:
            result.warn(f"\\input depth exceeded — skipping {target}")
            return ""
        return _resolve_source(target, result, depth + 1)

    return re.sub(r"\\(?:input|include)\{([^}]+)\}", _replace_input, text)


# ── top-level parse ──────────────────────────────────────────────────────────


def _parse_source(source: str, result: ParseResult) -> None:
    try:
        walker = LatexWalker(source)
        nodes, _, _ = walker.get_latex_nodes()
    except Exception as exc:  # noqa: BLE001
        result.warn(f"LaTeX walker failed: {exc} — attempting partial node extraction")
        return

    _walk_nodes(nodes, section_path=[], result=result)


# ── node walker ──────────────────────────────────────────────────────────────


def _walk_nodes(nodes: list, section_path: list[str], result: ParseResult) -> None:
    for node in nodes:
        try:
            _process_node(node, section_path, result)
        except Exception as exc:  # noqa: BLE001
            raw = getattr(node, "latex_verbatim", lambda n=node: repr(n))()
            result.warn(f"skipped node ({type(node).__name__}): {exc} — {raw[:80]!r}")


def _process_node(node, section_path: list[str], result: ParseResult) -> None:
    match node:
        case None:
            return

        case LatexMacroNode(macroname=name) if name in _SECTION_MACROS:
            argnlist = node.nodeargd.argnlist if node.nodeargd else []
            title = _node_to_text(argnlist[0]) if argnlist else name
            depth = list(_SECTION_MACROS).index(name)
            # mutate the list in-place so caller's reference stays in sync
            section_path[:] = section_path[:depth] + [title]

        case LatexEnvironmentNode(environmentname=env):
            raw = node.latex_verbatim()
            match env:
                case env if env in _MARKER_ENVS:
                    unit_id = _extract_marker_id(node) or f"{env}:{_content_hash(raw)}"
                    result.units.append(
                        Unit(
                            id=unit_id,
                            hash=_content_hash(raw),
                            raw=raw,
                            section_path=list(section_path),
                            refs=_extract_refs(raw),
                            symbols=_extract_symbols(raw),
                            marked=True,
                            marker_type=env,
                        )
                    )
                case env if env in _KNOWN_ENVS:
                    label = _extract_label(raw)
                    unit_id = label or f"{env}:{_content_hash(raw)}"
                    result.units.append(
                        Unit(
                            id=unit_id,
                            hash=_content_hash(raw),
                            raw=raw,
                            section_path=list(section_path),
                            refs=_extract_refs(raw),
                            symbols=_extract_symbols(raw),
                            marked=False,
                        )
                    )
                case _ if hasattr(node, "nodelist") and node.nodelist:
                    _walk_nodes(node.nodelist, section_path, result)


# ── helpers ──────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode()).hexdigest()[:16]


def _extract_symbols(text: str) -> list[str]:
    symbols: set[str] = set()
    for match in re.finditer(r"\$([^$]+)\$|\\\[(.+?)\\\]", text, re.DOTALL):
        fragment = match.group(1) or match.group(2) or ""
        symbols.update(re.findall(r"\\?[A-Za-z]+", fragment))
    return sorted(symbols)


def _extract_refs(text: str) -> list[str]:
    return re.findall(r"\\(?:ref|eqref|cite)\{([^}]+)\}", text)


def _node_to_text(node) -> str:
    if node is None:
        return ""
    if hasattr(node, "nodelist"):
        return "".join(_node_to_text(n) for n in node.nodelist if n)
    if hasattr(node, "chars"):
        return node.chars
    return ""


def _extract_label(raw: str) -> str | None:
    m = re.search(r"\\label\{([^}]+)\}", raw)
    return m.group(1) if m else None


def _extract_marker_id(node: LatexEnvironmentNode) -> str | None:
    try:
        args = node.nodeargd.argnlist if node.nodeargd else []
        return _node_to_text(args[0]).strip() or None if args else None
    except (AttributeError, IndexError):
        return None
