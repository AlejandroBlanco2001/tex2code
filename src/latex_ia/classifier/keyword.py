from __future__ import annotations

import re

from latex_ia.models import ClassificationResult, Role, Unit

# (pattern, role, weight)
_VOCAB: list[tuple[str, Role, float]] = [
    # spec signals
    (r"\bwe propose\b", Role.spec, 1.0),
    (r"\bwe define\b", Role.spec, 1.0),
    (r"\bwe minimize\b", Role.spec, 1.0),
    (r"\bthe loss is\b", Role.spec, 1.0),
    (r"\bwe set\b", Role.spec, 0.6),
    (r"\bhyperparameter\b", Role.spec, 0.7),
    (r"\bgiven by eq", Role.spec, 0.8),
    (r"\bwe train\b", Role.spec, 0.9),
    (r"\bwe implement\b", Role.spec, 1.0),
    (r"\bformally\b", Role.spec, 0.5),
    (r"\blet \w+ be\b", Role.spec, 0.7),
    (r"\balgorithm\b", Role.spec, 0.8),
    (r"\boptimize\b", Role.spec, 0.7),
    (r"\bour model\b", Role.spec, 0.8),
    (r"\bour approach\b", Role.spec, 0.8),
    # definition signals
    (r"\bwe denote\b", Role.definition, 0.9),
    (r"\bwe use \w+ to denote", Role.definition, 0.9),
    (r"\bnotation\b", Role.definition, 0.7),
    (r"\bwhere \w+ is\b", Role.definition, 0.5),
    # assumption signals
    (r"\bwe assume\b", Role.assumption, 1.0),
    (r"\bassume that\b", Role.assumption, 1.0),
    (r"\bwe require\b", Role.assumption, 0.7),
    # context signals (negative for spec)
    (r"\bprevious work\b", Role.context, 1.0),
    (r"\brelated to\b", Role.context, 0.6),
    (r"\bas shown by\b", Role.context, 0.9),
    (r"\bin contrast\b", Role.context, 0.7),
    (r"\bhas been studied\b", Role.context, 1.0),
    (r"\bin the literature\b", Role.context, 1.0),
    (r"\bwe review\b", Role.context, 0.9),
    (r"\bprior work\b", Role.context, 1.0),
    (r"\bsurvey\b", Role.context, 0.6),
    # result signals
    (r"\bwe observe\b", Role.result, 1.0),
    (r"\boutperforms\b", Role.result, 0.9),
    (r"\bperformance improve", Role.result, 0.9),
    (r"\bwe report\b", Role.result, 0.8),
    (r"\btable \d+ shows\b", Role.result, 0.9),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), role, w) for p, role, w in _VOCAB]

CONFIDENCE_THRESHOLD = 0.6


class KeywordScorer:
    """Tier 3: weighted vocabulary scorer. Zero external dependencies."""

    def classify(
        self, unit: Unit, threshold: float = CONFIDENCE_THRESHOLD
    ) -> ClassificationResult | None:
        scores: dict[Role, float] = {}
        text = unit.raw.lower()

        for pattern, role, weight in _COMPILED:
            if pattern.search(text):
                scores[role] = scores.get(role, 0.0) + weight

        if not scores:
            return None

        best_role = max(scores, key=lambda r: scores[r])
        total = sum(scores.values())
        confidence = scores[best_role] / total if total > 0 else 0.0

        if confidence < threshold:
            return None

        return ClassificationResult(
            unit_id=unit.id,
            role=best_role,
            confidence=round(confidence, 3),
            tier_used=3,
        )
