"""
Symbol glossary — tracks which unit defines each symbol and injects
relevant definitions into LLM prompts.

After a definition or assumption unit is processed, its symbols are
registered here.  Before any LLM call, resolve() returns the raw LaTeX
of all defining units whose symbols overlap with the target unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from latex_ia.models import Role, Unit

# Only units with these roles contribute definitions to the glossary.
_DEFINING_ROLES: frozenset[Role] = frozenset({Role.definition, Role.assumption})

# Short symbols (single letter, common noise like 'x', 'z', 'N') are too
# ubiquitous to be useful as glossary keys.
_MIN_SYMBOL_LEN = 3


@dataclass
class GlossaryEntry:
    """One symbol → source mapping stored in the glossary."""

    symbol: str
    raw: str  # LaTeX source of the defining unit
    unit_id: str
    role: Role


@dataclass
class Glossary:
    """Accumulates symbol definitions as units are processed."""

    _entries: dict[str, GlossaryEntry] = field(default_factory=dict)

    def update(self, unit: Unit, role: Role) -> None:
        """
        Register the symbols of *unit* if its role is definition or assumption.

        Existing entries are overwritten — later definitions win.
        """
        if role not in _DEFINING_ROLES:
            return
        for sym in unit.symbols:
            if len(sym) >= _MIN_SYMBOL_LEN:
                self._entries[sym] = GlossaryEntry(
                    symbol=sym,
                    raw=unit.raw,
                    unit_id=unit.id,
                    role=role,
                )

    def resolve(self, unit: Unit) -> list[GlossaryEntry]:
        """Return glossary entries whose symbol appears in *unit*'s symbol list."""
        return [
            self._entries[sym]
            for sym in unit.symbols
            if sym in self._entries and self._entries[sym].unit_id != unit.id
        ]

    def format_for_prompt(self, unit: Unit) -> str:
        """
        Return a formatted block of resolved definitions for injection into a prompt.

        Returns an empty string when there are no relevant entries.
        """
        entries = self.resolve(unit)
        if not entries:
            return ""

        seen_units: set[str] = set()
        parts: list[str] = ["--- resolved definitions ---"]

        for entry in entries:
            if entry.unit_id in seen_units:
                continue
            seen_units.add(entry.unit_id)
            parts.append(f"[definition  id={entry.unit_id}]\n{entry.raw.strip()}")

        parts.append("--- end definitions ---")
        return "\n\n".join(parts)

    def __len__(self) -> int:
        """Return the number of symbols currently in the glossary."""
        return len(self._entries)
