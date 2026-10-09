"""Fixtures shared across eval tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from latex_ia.models import Manifest, Unit
from latex_ia.parser import parse

SAMPLE_TEX = Path(__file__).parents[2] / "examples" / "sample_paper" / "paper.tex"
GENERATED = Path(__file__).parents[2] / ".tex2code" / "generated"


@pytest.fixture(scope="session")
def sample_units() -> list[Unit]:
    return parse(SAMPLE_TEX)


@pytest.fixture(scope="session")
def sample_unit_map(sample_units) -> dict[str, Unit]:
    return {u.id: u for u in sample_units}


@pytest.fixture(scope="session")
def sample_manifest() -> Manifest:
    manifest_path = Path(__file__).parents[2] / ".tex2code" / "manifest.json"
    if not manifest_path.exists():
        return Manifest()
    return Manifest.model_validate_json(manifest_path.read_text())
