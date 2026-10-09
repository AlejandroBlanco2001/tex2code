from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from latex_ia.models import Manifest, ManifestEntry, Role, Unit, UnitResult

_GENERATED = Path(".tex2code/generated")
_QUESTIONS = Path(".tex2code/questions.md")


def _stem(unit_id: str) -> str:
    """Derive a safe Python module name from a unit id."""
    # "impl:loss" → "loss",  "algorithm" → "algorithm",  "eq:abc123" → "eq_abc123"
    name = unit_id.split(":")[-1] if ":" in unit_id else unit_id
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return name.strip("_") or "unit"


def write_result(unit: Unit, result: UnitResult, manifest: Manifest) -> list[Path]:
    """
    Persist generated code and tests under .tex2code/generated/.
    Returns the list of files written (may be empty for non-spec roles).
    """
    written: list[Path] = []

    if result.role == Role.spec and result.code_stub:
        stem = _stem(unit.id)
        src_dir = _GENERATED / "src"
        test_dir = _GENERATED / "tests"
        src_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

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
