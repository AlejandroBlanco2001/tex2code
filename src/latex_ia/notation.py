"""Generate a notation guide mapping LaTeX symbols to units and code."""

from __future__ import annotations

from pathlib import Path

from latex_ia.models import Manifest, Unit


def generate_notation_guide(units: list[Unit], manifest: Manifest) -> str:
    """Return a Markdown table mapping every tracked symbol to its context."""
    rows: list[dict] = []
    seen: set[str] = set()

    for unit in units:
        if not unit.symbols:
            continue
        entry = manifest.entries.get(unit.id)
        role = entry.role.value if entry else "unknown"
        code_file = Path(entry.code[0]).name if (entry and entry.code) else "—"
        section = " › ".join(unit.section_path) if unit.section_path else "—"

        for sym in sorted(unit.symbols):
            if sym in seen:
                continue
            seen.add(sym)
            rows.append(
                {
                    "symbol": f"`{sym}`",
                    "unit": unit.id,
                    "role": role,
                    "section": section,
                    "code": code_file,
                }
            )

    if not rows:
        return "_No symbols tracked yet. Run `tex2code watch` to process the document._\n"

    header = "| Symbol | Defined in | Role | Section | Code file |\n"
    sep = "|--------|-----------|------|---------|----------|\n"
    body = "".join(
        f"| {r['symbol']} | `{r['unit']}` | {r['role']} | {r['section']} | {r['code']} |\n"
        for r in rows
    )
    return header + sep + body


def write_notation_guide(units: list[Unit], manifest: Manifest) -> Path:
    """Write the notation guide to .tex2code/notation.md and return its path."""
    out = Path(".tex2code/notation.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_notation_guide(units, manifest), encoding="utf-8")
    return out
