"""Write \\begin{implement}...\\end{implement} markers back into a .tex file."""

from __future__ import annotations

from pathlib import Path


def mark_unit_in_file(tex_path: Path, unit_raw: str) -> bool:
    """Wrap *unit_raw* in implement markers in the tex file. Returns True on success."""
    content = tex_path.read_text(encoding="utf-8")
    idx = content.find(unit_raw)
    if idx == -1:
        return False
    # Check if already wrapped
    prefix = content[max(0, idx - 40) : idx].rstrip()
    if prefix.endswith("\\begin{implement}"):
        return False
    new_content = (
        content[:idx]
        + "\\begin{implement}\n"
        + unit_raw
        + "\n\\end{implement}"
        + content[idx + len(unit_raw) :]
    )
    tex_path.write_text(new_content, encoding="utf-8")
    return True
