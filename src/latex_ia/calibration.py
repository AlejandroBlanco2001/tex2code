"""Domain calibration — auto-infer profile fields and run interactive Q&A."""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from latex_ia.models import Profile

console = Console()

_RE_ALGORITHM = re.compile(r"\\begin\{algorithm")
_RE_EQ_LABEL = re.compile(r"\\label\{eq:")

# Style files → known venue/field hints
_STYLE_HINTS: dict[str, dict] = {
    "neurips": {"field": "machine-learning", "venue_type": "conference"},
    "icml": {"field": "machine-learning", "venue_type": "conference"},
    "iclr": {"field": "machine-learning", "venue_type": "conference"},
    "cvpr": {"field": "computer-vision", "venue_type": "conference"},
    "acl": {"field": "nlp", "venue_type": "conference"},
    "nips": {"field": "machine-learning", "venue_type": "conference"},
    "nature": {"field": "biology", "venue_type": "journal"},
    "pnas": {"field": "biology", "venue_type": "journal"},
    "econometrica": {"field": "economics", "venue_type": "journal"},
}

_HEURISTIC_KEYWORDS = {
    "machine-learning": ["loss", "gradient", "neural", "train", "epoch", "batch"],
    "computer-vision": ["image", "pixel", "convolution", "segmentation", "detection"],
    "nlp": ["token", "vocabulary", "embedding", "attention", "language model"],
    "biology": ["protein", "sequence", "gene", "cell", "expression"],
    "economics": ["utility", "equilibrium", "market", "welfare", "elasticity"],
    "formal-math": ["theorem", "proof", "lemma", "corollary", "proposition"],
}


def infer_from_source(tex_path: Path) -> Profile:
    """Auto-infer profile fields from document content — no user input."""
    profile = Profile()
    if not tex_path.exists():
        return profile

    src = tex_path.read_text(encoding="utf-8", errors="ignore").lower()

    # Style file hints
    for key, hints in _STYLE_HINTS.items():
        if key in src:
            profile = profile.model_copy(update=hints)
            break

    # Keyword-based field detection (if not already found)
    if profile.field == "unknown":
        scores: dict[str, int] = {}
        for field, keywords in _HEURISTIC_KEYWORDS.items():
            scores[field] = sum(src.count(kw) for kw in keywords)
        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0:
            profile = profile.model_copy(update={"field": best})

    # Spec heuristics from document structure
    heuristics: list[str] = []
    if _RE_ALGORITHM.search(src):
        heuristics.append("algorithms-are-spec")
    if _RE_EQ_LABEL.search(src):
        heuristics.append("labeled-equations-are-spec")
    if heuristics:
        profile = profile.model_copy(update={"spec_heuristics": heuristics})

    return profile


def run_interactive(profile: Profile) -> Profile:
    """Ask the researcher 4–6 targeted questions, pre-populated with inferences."""
    console.print(
        Panel(
            "[bold]tex2code — domain calibration[/bold]\n"
            "Answer a few questions so the agent can tailor its output.\n"
            "Press Enter to accept the default shown in [brackets].",
            expand=False,
        )
    )

    updates: dict = {}

    field = typer.prompt("Research field / subfield", default=profile.field)
    updates["field"] = field

    edu = typer.prompt(
        "Education level (undergrad / masters / phd / postdoc)",
        default=profile.education_level,
    )
    updates["education_level"] = edu

    audience = typer.prompt(
        "Primary audience for the generated code (you / labmates / engineers / public)",
        default=profile.audience,
    )
    updates["audience"] = audience

    reads_python = typer.confirm(
        "Are you comfortable reading Python?",
        default=profile.code_reader_expertise == "reads-python",
    )
    updates["code_reader_expertise"] = "reads-python" if reads_python else "math-only"

    model = typer.prompt(
        "LLM model to use (any LiteLLM model string)",
        default=profile.model,
    )
    updates["model"] = model

    # Only ask about proofs for math-heavy papers
    if "theorem" in " ".join(profile.spec_heuristics) or field in ("formal-math",):
        proofs = typer.confirm(
            "Are the proofs themselves the spec (implement them), or do they justify an algorithm?",
            default=False,
        )
        updates["proofs_are_spec"] = proofs

    return profile.model_copy(update=updates)


def calibrate(tex_path: Path, *, interactive: bool = True) -> Profile:
    """Full calibration: auto-infer then optionally ask questions."""
    profile = infer_from_source(tex_path)
    if interactive:
        profile = run_interactive(profile)
    return profile
