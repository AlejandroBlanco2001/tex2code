"""
Dependency graph over parsed units.

Edges are derived from explicit \\ref/\\cite links (unit A refs unit B → B
must precede A) and from direct symbol overlap between a definition unit and
any unit that uses those symbols.

Topological sort (Kahn's algorithm) gives a processing order that guarantees
every dependency is processed before the units that depend on it.  Cycles —
rare in well-formed papers — are broken by falling back to document order.
"""

from __future__ import annotations

from collections import deque

from latex_ia.models import Role, Unit

# Roles whose units are treated as definers of their symbols.
_DEFINING_ROLES: frozenset[Role] = frozenset({Role.definition, Role.assumption})


def build_dependency_map(
    units: list[Unit],
    role_hints: dict[str, Role] | None = None,
) -> dict[str, set[str]]:
    """
    Return a map of unit_id → set of unit_ids that must be processed before it.

    *role_hints* maps unit_id → Role for units already classified (e.g. from
    the manifest or rule classifier).  Without hints, only explicit \\ref links
    are used; with hints, definition/assumption units seed the symbol index.
    """
    id_set: set[str] = {u.id for u in units}
    deps: dict[str, set[str]] = {u.id: set() for u in units}

    # Index: symbol name → set of unit_ids that define it
    symbol_definers: dict[str, set[str]] = {}
    hints = role_hints or {}

    for unit in units:
        role = hints.get(unit.id)
        if role in _DEFINING_ROLES:
            for sym in unit.symbols:
                if len(sym) > 2:  # skip single-letter symbols (x, z, N …)
                    symbol_definers.setdefault(sym, set()).add(unit.id)

    for unit in units:
        # Explicit \ref / \cite links
        for ref in unit.refs:
            if ref in id_set and ref != unit.id:
                deps[unit.id].add(ref)

        # Symbol-based links: unit uses a symbol defined elsewhere
        for sym in unit.symbols:
            for definer_id in symbol_definers.get(sym, set()):
                if definer_id != unit.id:
                    deps[unit.id].add(definer_id)

    return deps


def topological_sort(
    units: list[Unit],
    deps: dict[str, set[str]],
) -> list[Unit]:
    """
    Return *units* in an order where every dependency precedes its dependents.

    Uses Kahn's algorithm.  Units involved in cycles are appended in their
    original document order after all acyclic units have been emitted.
    """
    id_to_unit: dict[str, Unit] = {u.id: u for u in units}

    # Build adjacency list in the direction needed by Kahn's:
    # edge  B → A  means "B precedes A" (A depends on B)
    successors: dict[str, set[str]] = {u.id: set() for u in units}
    in_degree: dict[str, int] = {u.id: 0 for u in units}

    for unit_id, unit_deps in deps.items():
        for dep_id in unit_deps:
            if dep_id in successors:
                successors[dep_id].add(unit_id)
                in_degree[unit_id] += 1

    queue: deque[str] = deque(uid for uid in in_degree if in_degree[uid] == 0)
    ordered: list[Unit] = []

    while queue:
        uid = queue.popleft()
        ordered.append(id_to_unit[uid])
        for successor in successors[uid]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    # Append any units caught in cycles (document order preserved)
    processed = {u.id for u in ordered}
    for unit in units:
        if unit.id not in processed:
            ordered.append(unit)

    return ordered
