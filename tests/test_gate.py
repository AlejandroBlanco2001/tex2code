from latex_ia.classifier.gate import gate
from latex_ia.models import Manifest, ManifestEntry, ProcessMode, Role, Unit


def _unit(marked: bool, hash_: str = "abc123", id_: str = "impl:loss") -> Unit:
    return Unit(
        id=id_,
        hash=hash_,
        raw="content",
        marked=marked,
        marker_type="implement" if marked else None,
    )


def test_tier_minus1_unmarked_unit_skipped():
    result = gate(_unit(marked=False), Manifest())
    assert result is not None
    assert result.skipped is True
    assert result.tier_used == -1


def test_tier_0_unchanged_hash_skipped():
    manifest = Manifest(
        entries={
            "impl:loss": ManifestEntry(hash="abc123", role=Role.spec, last_processed="2026-10-09")
        }
    )
    result = gate(_unit(marked=True, hash_="abc123"), manifest)
    assert result is not None
    assert result.skipped is True
    assert result.tier_used == 0
    assert result.role == Role.spec


def test_tier_0_changed_hash_proceeds():
    manifest = Manifest(
        entries={
            "impl:loss": ManifestEntry(hash="old_hash", role=Role.spec, last_processed="2026-10-09")
        }
    )
    result = gate(_unit(marked=True, hash_="new_hash"), manifest)
    assert result is None  # signal to proceed


def test_marked_new_unit_proceeds():
    result = gate(_unit(marked=True), Manifest())
    assert result is None  # no manifest entry → proceed


class TestScanMode:
    def test_unmarked_unit_proceeds_in_scan(self):
        result = gate(_unit(marked=False), Manifest(), ProcessMode.scan)
        assert result is None  # Tier -1 skipped in scan mode

    def test_unmarked_unit_proceeds_in_auto(self):
        result = gate(_unit(marked=False), Manifest(), ProcessMode.auto)
        assert result is None

    def test_hash_cache_still_applies_in_scan(self):
        manifest = Manifest(
            entries={
                "impl:loss": ManifestEntry(
                    hash="abc123", role=Role.spec, last_processed="2026-10-09"
                )
            }
        )
        result = gate(_unit(marked=False, hash_="abc123"), manifest, ProcessMode.scan)
        assert result is not None
        assert result.skipped is True
        assert result.tier_used == 0

    def test_strict_is_default(self):
        result = gate(_unit(marked=False), Manifest())
        assert result is not None and result.tier_used == -1
