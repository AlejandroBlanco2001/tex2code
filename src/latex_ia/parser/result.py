"""ParseResult dataclass — collects units and warnings from a parse pass."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from latex_ia.models import Unit

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Accumulates parsed units and warnings without raising on partial failures."""

    units: list[Unit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = ""  # full inlined LaTeX source (all \input files merged)

    def warn(self, msg: str) -> None:
        """Record a warning to both the logger and the warnings list."""
        logger.warning(msg)
        self.warnings.append(msg)
