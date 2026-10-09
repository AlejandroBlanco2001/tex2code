from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from latex_ia.models import Manifest, ManifestEntry, Role, Unit, UnitResult

_GENERATED = Path(".tex2code/generated")
_QUESTIONS = Path(".tex2code/questions.md")

_RE_HEX = re.compile(r"^[0-9a-f]+$")
_RE_SECTION_NUM = re.compile(r"^[\d.\s]+")
_RE_NONALPHA = re.compile(r"[^a-zA-Z\s]")
_RE_LABEL = re.compile(r"\\label\{([^}]+)\}")
_SECTION_STOP = frozenset({"and", "the", "of", "in", "for", "a", "an", "with", "on"})


def _is_hash(name: str) -> bool:
    return len(name) >= 8 and bool(_RE_HEX.match(name))


def _name_from_section(section_path: list[str], unit_type: str) -> str:
    """Derive a snake_case name from the most specific section heading."""
    if not section_path:
        return unit_type
    section = _RE_SECTION_NUM.sub("", section_path[-1]).strip()
    section = _RE_NONALPHA.sub(" ", section)
    words = [w.lower() for w in section.split() if w.lower() not in _SECTION_STOP][:4]
    return "_".join(words) if words else unit_type


def _name_from_label(raw: str) -> str | None:
    """Extract a snake_case name from the first \\label{} in the unit's raw LaTeX."""
    m = _RE_LABEL.search(raw)
    if not m:
        return None
    label = m.group(1)
    # Strip common prefixes (eq:, fig:, tab:, alg:) and convert to snake_case.
    label = re.sub(r"^[a-z]{1,4}:", "", label)
    name = re.sub(r"[^a-zA-Z0-9_]", "_", label)
    return name.strip("_") or None


def _stem(unit: Unit) -> str:
    """Derive a readable Python module name from a unit."""
    uid = unit.id
    suffix = uid.split(":")[-1] if ":" in uid else uid
    unit_type = uid.split(":")[0] if ":" in uid else "unit"

    if _is_hash(suffix):
        # Prefer: label inside raw → section path → unit type.
        from_label = _name_from_label(unit.raw)
        if from_label:
            return from_label
        return _name_from_section(unit.section_path, unit_type)

    name = re.sub(r"[^a-zA-Z0-9_]", "_", suffix)
    return name.strip("_") or "unit"


def _unique_stem(stem: str, src_dir: Path) -> str:
    """Return *stem* unchanged if the target file does not exist; otherwise append the hash suffix."""
    if not (src_dir / f"{stem}.py").exists():
        return stem
    # Find a free name by appending incrementing suffixes.
    for i in range(2, 100):
        candidate = f"{stem}_{i}"
        if not (src_dir / f"{candidate}.py").exists():
            return candidate
    return stem  # give up — caller will overwrite


def write_result(unit: Unit, result: UnitResult, manifest: Manifest) -> list[Path]:
    """
    Persist generated code and tests under .tex2code/generated/.
    Returns the list of files written (may be empty for non-spec roles).
    """
    written: list[Path] = []

    if result.role == Role.spec and result.code_stub:
        src_dir = _GENERATED / "src"
        test_dir = _GENERATED / "tests"
        src_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        stem = _unique_stem(_stem(unit), src_dir)
        src_file = src_dir / f"{stem}.py"
        src_file.write_text(result.code_stub, encoding="utf-8")
        written.append(src_file)

        if result.test_stub:
            test_file = test_dir / f"test_{stem}.py"
            test_file.write_text(result.test_stub, encoding="utf-8")
            written.append(test_file)

    if result.open_questions:
        _append_questions(unit.id, result.open_questions)

    # Update manifest
    manifest.entries[unit.id] = ManifestEntry(
        hash=unit.hash,
        role=result.role,
        last_processed=date.today().isoformat(),
        code=[str(p) for p in written if "src" in str(p)],
        tests=[str(p) for p in written if "test" in str(p)],
    )

    return written


def _append_questions(unit_id: str, questions: list[str]) -> None:
    _QUESTIONS.parent.mkdir(parents=True, exist_ok=True)
    with _QUESTIONS.open("a", encoding="utf-8") as f:
        f.write(f"\n## {unit_id}\n")
        for q in questions:
            f.write(f"- {q}\n")
