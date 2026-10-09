from __future__ import annotations

from latex_ia.models import Unit

_WINDOW = 3  # units on each side of the target


def build_context(target: Unit, all_units: list[Unit]) -> str:
    """
    Return a section-scoped text slice for LLM prompts.

    Includes up to _WINDOW units before and after the target, formatted
    with section headings so the LLM understands position in the document.
    No retrieval — built directly from the parsed unit list at call time.
    """
    try:
        idx = next(i for i, u in enumerate(all_units) if u.id == target.id)
    except StopIteration:
        return target.raw

    start = max(0, idx - _WINDOW)
    end = min(len(all_units), idx + _WINDOW + 1)
    window = all_units[start:end]

    parts = []
    for u in window:
        section = " > ".join(u.section_path) if u.section_path else "(preamble)"
        label = f"[{section}]  id={u.id}"
        if u.id == target.id:
            label += "  ← TARGET"
        parts.append(f"{label}\n{u.raw.strip()}")

    return "\n\n---\n\n".join(parts)
