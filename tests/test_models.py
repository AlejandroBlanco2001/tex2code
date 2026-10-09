from latex_ia.models import ClassificationResult, Manifest, ManifestEntry, Role, Unit


def test_unit_defaults():
    u = Unit(id="sec:intro", hash="abc", raw="some text")
    assert u.marked is False
    assert u.refs == []
    assert u.symbols == []


def test_unit_marked():
    u = Unit(id="impl:loss", hash="abc", raw="loss eq", marked=True, marker_type="implement")
    assert u.marked is True
    assert u.marker_type == "implement"


def test_classification_result_confidence_bounds():
    r = ClassificationResult(unit_id="x", role=Role.spec, confidence=0.95, tier_used=3)
    assert 0.0 <= r.confidence <= 1.0


def test_manifest_empty():
    m = Manifest()
    assert m.entries == {}


def test_manifest_entry():
    e = ManifestEntry(hash="abc", role=Role.spec, last_processed="2026-10-09")
    assert e.code == []
    assert e.outputs == []
