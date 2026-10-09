from pathlib import Path

import pytest

from latex_ia.models import Unit
from latex_ia.parser import parse

EXAMPLES = Path(__file__).parents[2] / "examples"
ATTENTION_TEX = EXAMPLES / "attention" / "ms.tex"
VAE_TEX = EXAMPLES / "vae" / "iclr14_sva.tex"


@pytest.fixture(scope="session")
def attention_units() -> list[Unit]:
    return parse(ATTENTION_TEX)


@pytest.fixture(scope="session")
def vae_units() -> list[Unit]:
    return parse(VAE_TEX)
