"""Load and save the .tex2code/manifest.json file."""

from __future__ import annotations

import json
from pathlib import Path

from latex_ia.models import Manifest, ManifestEntry, Role

_DEFAULT_PATH = Path(".tex2code/manifest.json")


def load(path: Path = _DEFAULT_PATH) -> Manifest:
    """
    Load the manifest from *path*.

    Returns an empty Manifest if the file does not exist.
    """
    if not path.exists():
        return Manifest()

    data = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, ManifestEntry] = {}
    for unit_id, v in data.items():
        entries[unit_id] = ManifestEntry(
            hash=v["hash"],
            role=Role(v["role"]),
            last_processed=v["last_processed"],
            code=v.get("code", []),
            tests=v.get("tests", []),
            outputs=v.get("outputs", []),
        )
    return Manifest(entries=entries)


def save(manifest: Manifest, path: Path = _DEFAULT_PATH) -> None:
    """Serialise *manifest* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, dict] = {}
    for unit_id, e in manifest.entries.items():
        data[unit_id] = {
            "hash": e.hash,
            "role": e.role.value,
            "last_processed": e.last_processed,
            "code": e.code,
            "tests": e.tests,
            "outputs": e.outputs,
        }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
