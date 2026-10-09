"""Walk a pylatexenc node tree and emit Unit objects into a ParseResult."""

from __future__ import annotations

from pylatexenc.latexwalker import LatexEnvironmentNode, LatexMacroNode, LatexWalker

from latex_ia.models import Unit
from latex_ia.parser.helpers import (
    content_hash,
    extract_label,
    extract_refs,
    extract_symbols,
    node_to_text,
)
from latex_ia.parser.result import ParseResult

# Section macros mapped to nesting depth (order matters for path trimming).
_SECTION_DEPTH: dict[str, int] = {
    "section": 0,
    "subsection": 1,
    "subsubsection": 2,
    "paragraph": 3,
}

_MARKER_ENVS: frozenset[str] = frozenset({"tcprocess", "implement"})
_KNOWN_ENVS: frozenset[str] = frozenset(
    {
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
)


def parse_source(source: str, result: ParseResult) -> None:
    """Parse *source* LaTeX and append discovered units to *result*."""
    try:
        walker = LatexWalker(source)
        nodes, _, _ = walker.get_latex_nodes()
    except Exception as exc:  # noqa: BLE001
        result.warn(f"LaTeX walker failed: {exc} — attempting partial node extraction")
        return
    _walk_nodes(nodes, section_path=[], result=result)


def _walk_nodes(nodes: list, section_path: list[str], result: ParseResult) -> None:
    """Iterate *nodes*, routing each to _process_node with shared section state."""
    for node in nodes:
        try:
            _process_node(node, section_path, result)
        except Exception as exc:  # noqa: BLE001
            raw = getattr(node, "latex_verbatim", lambda n=node: repr(n))()
            result.warn(f"skipped node ({type(node).__name__}): {exc} — {raw[:80]!r}")


def _process_node(node, section_path: list[str], result: ParseResult) -> None:
    """Dispatch a single node: update section path or emit a Unit."""
    match node:
        case None:
            return

        case LatexMacroNode(macroname=name) if name in _SECTION_DEPTH:
            argnlist = node.nodeargd.argnlist if node.nodeargd else []
            # Title is the last arg ([None, None, GroupNode] for \section{T},
            # [CharsNode('*'), None, GroupNode] for \section*{T}).
            title = node_to_text(argnlist[-1]) if argnlist else name
            depth = _SECTION_DEPTH[name]
            # Mutate in-place so the caller's reference stays in sync.
            section_path[:] = section_path[:depth] + [title]

        case LatexEnvironmentNode(environmentname=env):
            _process_env(node, env, section_path, result)


def _process_env(
    node: LatexEnvironmentNode,
    env: str,
    section_path: list[str],
    result: ParseResult,
) -> None:
    """Emit a Unit for a known or marker environment, or recurse into unknown ones."""
    raw = node.latex_verbatim()

    if env in _MARKER_ENVS:
        unit_id = _extract_marker_id(node) or f"{env}:{content_hash(raw)}"
        result.units.append(
            Unit(
                id=unit_id,
                hash=content_hash(raw),
                raw=raw,
                section_path=list(section_path),
                refs=extract_refs(raw),
                symbols=extract_symbols(raw),
                marked=True,
                marker_type=env,
            )
        )
        return

    if env in _KNOWN_ENVS:
        label = extract_label(raw)
        unit_id = label or f"{env}:{content_hash(raw)}"
        result.units.append(
            Unit(
                id=unit_id,
                hash=content_hash(raw),
                raw=raw,
                section_path=list(section_path),
                refs=extract_refs(raw),
                symbols=extract_symbols(raw),
                marked=False,
            )
        )
        return

    # Unknown environment — recurse into its body.
    if hasattr(node, "nodelist") and node.nodelist:
        _walk_nodes(node.nodelist, section_path, result)


def _extract_marker_id(node: LatexEnvironmentNode) -> str | None:
    """Return the optional label argument of a marker environment, or None.

    pylatexenc doesn't know our custom environments take an argument, so it
    parks {label} as the first LatexGroupNode in the body rather than in
    nodeargd.argnlist.  Check argnlist first, then fall back to nodelist[0].
    """
    try:
        args = node.nodeargd.argnlist if node.nodeargd else []
        if args:
            return node_to_text(args[0]).strip() or None
    except (AttributeError, IndexError):
        pass
    # Fall back: first child node is the {label} group placed in the body.
    try:
        from pylatexenc.latexwalker import LatexGroupNode

        first = node.nodelist[0] if node.nodelist else None
        if isinstance(first, LatexGroupNode):
            text = node_to_text(first).strip()
            return text or None
    except (AttributeError, IndexError):
        pass
    return None
