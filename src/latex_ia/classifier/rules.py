from __future__ import annotations

from latex_ia.models import ClassificationResult, Role, Unit

# Section title patterns → role
_CONTEXT_TITLES = {
    "introduction",
    "related work",
    "background",
    "motivation",
    "conclusion",
    "conclusions",
    "discussion",
    "acknowledgments",
    "acknowledgements",
    "abstract",
    "future work",
}
_RESULT_TITLES = {
    "results",
    "experiments",
    "evaluation",
    "ablation",
    "analysis",
}
_SPEC_TITLES = {
    "method",
    "methods",
    "methodology",
    "model",
    "approach",
    "algorithm",
    "framework",
    "architecture",
    "formulation",
}
_DEFINITION_TITLES = {
    "notation",
    "preliminaries",
    "definitions",
    "setup",
    "problem formulation",
}

# Environment name → role (always wins for known envs)
_ENV_ROLES: dict[str, Role] = {
    "algorithm": Role.spec,
    "algorithmic": Role.spec,
    "definition": Role.definition,
    "assumption": Role.assumption,
    "theorem": Role.definition,
    "lemma": Role.definition,
    "implement": Role.spec,
}


class RuleClassifier:
    """Tier 2: assign roles by section title and environment type."""

    CONFIDENCE = 0.9

    def classify(self, unit: Unit) -> ClassificationResult | None:
        # implement marker → always spec
        if unit.marker_type == "implement":
            return ClassificationResult(
                unit_id=unit.id,
                role=Role.spec,
                confidence=1.0,
                tier_used=1,
            )

        # known environment
        env = self._env_from_id(unit.id)
        if env and env in _ENV_ROLES:
            return ClassificationResult(
                unit_id=unit.id,
                role=_ENV_ROLES[env],
                confidence=self.CONFIDENCE,
                tier_used=2,
            )

        # section title match
        role = self._role_from_section(unit.section_path)
        if role:
            return ClassificationResult(
                unit_id=unit.id,
                role=role,
                confidence=self.CONFIDENCE,
                tier_used=2,
            )

        return None

    def _role_from_section(self, path: list[str]) -> Role | None:
        for title in path:
            t = title.lower().strip()
            match t:
                case t if t in _CONTEXT_TITLES:
                    return Role.context
                case t if t in _RESULT_TITLES:
                    return Role.result
                case t if t in _SPEC_TITLES:
                    return Role.spec
                case t if t in _DEFINITION_TITLES:
                    return Role.definition
        return None

    def _env_from_id(self, unit_id: str) -> str | None:
        # "algorithm:abc123" → "algorithm";  "algorithm" (label) → "algorithm"
        prefix = unit_id.split(":")[0] if ":" in unit_id else unit_id
        return prefix if prefix in _ENV_ROLES else None
