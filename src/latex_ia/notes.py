"""Persistent store for answered/dismissed questions with Jaccard similarity lookup."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_NOTES_FILE = Path(".tex2code/answered.json")
_RE_WORD = re.compile(r"\b\w{3,}\b")


@dataclass
class NoteEntry:
    question: str
    answer: str
    unit_id: str
    dismissed: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def load_notes() -> list[NoteEntry]:
    if not _NOTES_FILE.exists():
        return []
    try:
        return [NoteEntry(**e) for e in json.loads(_NOTES_FILE.read_text())]
    except Exception:
        return []


def save_note(question: str, answer: str, unit_id: str, *, dismissed: bool = False) -> None:
    notes = load_notes()
    for n in notes:
        if n.question == question and n.unit_id == unit_id:
            n.answer = answer
            n.dismissed = dismissed
            n.timestamp = datetime.now(UTC).isoformat()
            break
    else:
        notes.append(
            NoteEntry(question=question, answer=answer, unit_id=unit_id, dismissed=dismissed)
        )
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _NOTES_FILE.write_text(json.dumps([asdict(n) for n in notes], indent=2))


def _words(text: str) -> frozenset[str]:
    return frozenset(_RE_WORD.findall(text.lower()))


def find_prior_answer(
    question: str, notes: list[NoteEntry], *, threshold: float = 0.55
) -> NoteEntry | None:
    """Return the best-matching answered note, or None if similarity < threshold."""
    q_words = _words(question)
    if not q_words:
        return None
    best: NoteEntry | None = None
    best_score = 0.0
    for note in notes:
        if note.dismissed or not note.answer:
            continue
        n_words = _words(note.question)
        if not n_words:
            continue
        score = len(q_words & n_words) / len(q_words | n_words)
        if score > best_score:
            best_score = score
            best = note
    return best if best_score >= threshold else None
