from latex_ia.classifier.keyword import KeywordScorer
from latex_ia.models import Role, Unit


def _unit(raw: str, marked: bool = True) -> Unit:
    return Unit(id="test:unit", hash="abc", raw=raw, marked=marked)


scorer = KeywordScorer()


def test_spec_signal():
    u = _unit("We propose a new model. Formally, we define the loss as follows.")
    r = scorer.classify(u)
    assert r is not None
    assert r.role == Role.spec


def test_context_signal():
    u = _unit("Previous work has shown that deep networks fail. In the literature, this is known.")
    r = scorer.classify(u)
    assert r is not None
    assert r.role == Role.context


def test_assumption_signal():
    u = _unit("We assume the noise is Gaussian and i.i.d.")
    r = scorer.classify(u)
    assert r is not None
    assert r.role == Role.assumption


def test_low_signal_returns_none():
    u = _unit("The cat sat on the mat.")
    r = scorer.classify(u)
    assert r is None


def test_confidence_in_range():
    u = _unit("We train the model for 100 epochs. We minimize the cross-entropy loss.")
    r = scorer.classify(u)
    assert r is not None
    assert 0.0 <= r.confidence <= 1.0
