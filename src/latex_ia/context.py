"""
Build the context slice sent to the LLM for each unit.

Combines two complementary sources:
  1. Positional window — the ±_WINDOW units surrounding the target in
     document order (local prose context).
  2. Glossary injection — raw LaTeX of definition/assumption units whose
     symbols overlap with the target (semantic dependency context).
"""

from __future__ import annotations

from latex_ia.models import Unit

_WINDOW = 3  # units on each side of the target


def build_context(
    target: Unit,
    all_units: list[Unit],
    glossary=None,  # Glossary | None — avoids circular import
) -> str:
    """
    Return the context string for an LLM prompt about *target*.

    Includes up to _WINDOW positional neighbours plus any resolved symbol
    definitions from *glossary*.  Both sections are clearly labelled so the
    LLM can distinguish local context from imported definitions.
    """
    positional = _positional_window(target, all_units)
    resolved = glossary.format_for_prompt(target) if glossary is not None else ""

    if resolved:
        return f"{positional}\n\n{resolved}"
    return positional


def _positional_window(target: Unit, all_units: list[Unit]) -> str:
    """Return the ±_WINDOW unit slice around *target* as a formatted string."""
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
