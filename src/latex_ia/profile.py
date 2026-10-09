"""Load and save the .tex2code/profile.json calibration file."""

from __future__ import annotations

from pathlib import Path

from latex_ia.models import Profile

_DEFAULT_PATH = Path(".tex2code/profile.json")


def load(path: Path = _DEFAULT_PATH) -> Profile:
    """Load the profile from *path*, returning a default Profile if absent."""
    if not path.exists():
        return Profile()
    return Profile.model_validate_json(path.read_text(encoding="utf-8"))


def save(profile: Profile, path: Path = _DEFAULT_PATH) -> None:
    """Serialise *profile* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
