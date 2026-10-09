from __future__ import annotations

from latex_ia.models import ClassificationResult, Manifest, ProcessMode, Role, Unit


def gate(
    unit: Unit,
    manifest: Manifest,
    mode: ProcessMode = ProcessMode.strict,
) -> ClassificationResult | None:
    """
    Tiers -1 and 0 of the classification gate.

    Returns a ClassificationResult with skipped=True if the unit should be
    excluded from the pipeline, or None to signal it should proceed to
    rule/keyword/LLM classification.

    In strict mode (default) unmarked units are invisible (Tier -1).
    In scan/auto mode the Tier -1 check is skipped so every parsed unit
    flows through the rule and keyword classifiers.
    """
    # Tier -1: no opt-in marker → invisible to the pipeline (strict only)
    if mode == ProcessMode.strict and not unit.marked:
        return ClassificationResult(
            unit_id=unit.id,
            role=Role.unknown,
            confidence=1.0,
            tier_used=-1,
            skipped=True,
        )

    # Tier 0: hash unchanged since last run → already processed, skip
    entry = manifest.entries.get(unit.id)
    if entry and entry.hash == unit.hash:
        return ClassificationResult(
            unit_id=unit.id,
            role=entry.role,
            confidence=1.0,
            tier_used=0,
            skipped=True,
        )

    return None
