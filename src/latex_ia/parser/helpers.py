"""Low-level LaTeX text utilities used by the walker and resolver."""

from __future__ import annotations

import hashlib
import re

_RE_NORMALIZE = re.compile(r"\s+")
_RE_MATH = re.compile(r"\$([^$]+)\$|\\\[(.+?)\\\]", re.DOTALL)
_RE_WORD = re.compile(r"\\?[A-Za-z]+")
_RE_REF = re.compile(r"\\(?:ref|eqref|cite)\{([^}]+)\}")
_RE_LABEL = re.compile(r"\\label\{([^}]+)\}")


def normalize(text: str) -> str:
    """Collapse whitespace to a single space and strip leading/trailing."""
    return _RE_NORMALIZE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """Return a 16-hex-char SHA-256 digest of the normalised text."""
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:16]


def extract_symbols(text: str) -> list[str]:
    """Return sorted unique math symbols found in inline and display math."""
    symbols: set[str] = set()
    for match in _RE_MATH.finditer(text):
        fragment = match.group(1) or match.group(2) or ""
        symbols.update(_RE_WORD.findall(fragment))
    return sorted(symbols)


def extract_refs(text: str) -> list[str]:
    """Return all \\ref, \\eqref, and \\cite targets in the text."""
    return _RE_REF.findall(text)


def extract_label(raw: str) -> str | None:
    """Return the first \\label{...} value found in raw, or None."""
    m = _RE_LABEL.search(raw)
    return m.group(1) if m else None


def node_to_text(node) -> str:
    """Recursively flatten a pylatexenc node tree to plain text."""
    if node is None:
        return ""
    if hasattr(node, "nodelist"):
        return "".join(node_to_text(n) for n in node.nodelist if n)
    if hasattr(node, "chars"):
        return node.chars
    return ""
