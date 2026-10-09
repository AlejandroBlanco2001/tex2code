from __future__ import annotations

import json
from pathlib import Path

from latex_ia.models import Manifest, ManifestEntry, Role

_DEFAULT_PATH = Path(".tex2code/manifest.json")


def load(path: Path = _DEFAULT_PATH) -> Manifest:
    if not path.exists():
        return Manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = {
        k: ManifestEntry(
            hash=v["hash"],
            role=Role(v["role"]),
            last_processed=v["last_processed"],
            code=v.get("code", []),
            tests=v.get("tests", []),
            outputs=v.get("outputs", []),
        )
        for k, v in data.items()
    }
    return Manifest(entries=entries)


def save(manifest: Manifest, path: Path = _DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        k: {
            "hash": e.hash,
            "role": e.role.value,
            "last_processed": e.last_processed,
            "code": e.code,
            "tests": e.tests,
            "outputs": e.outputs,
        }
        for k, e in manifest.entries.items()
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
