"""LLM-judged fidelity between generated code and LaTeX spec.

Requires real LLM calls — costs money. Run with: make eval
These are excluded from `make test` and `make test-all`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.evals.judge import judge

pytestmark = pytest.mark.eval

GENERATED_SRC = Path(__file__).parents[2] / ".tex2code" / "generated" / "src"


def _load(filename: str) -> str:
    path = GENERATED_SRC / filename
    if not path.exists():
        pytest.skip(f"generated file not found: {path}")
    return path.read_text()


class TestGnnFidelity:
    def test_implements_mean_aggregation(self, sample_unit_map):
        code = _load("gnn.py")
        unit = sample_unit_map["model:gnn"]
        judge(
            criterion=(
                "The code computes mean-aggregated neighbour embeddings: "
                "sum h_u over neighbours divided by |N(v)|"
            ),
            context=unit.raw,
            output=code,
            threshold=0.7,
        )

    def test_applies_relu_activation(self, sample_unit_map):
        code = _load("gnn.py")
        unit = sample_unit_map["model:gnn"]
        judge(
            criterion="The code applies a ReLU activation (not sigmoid or tanh)",
            context=unit.raw,
            output=code,
            threshold=0.7,
        )

    def test_uses_weight_matrix(self, sample_unit_map):
        code = _load("gnn.py")
        unit = sample_unit_map["model:gnn"]
        judge(
            criterion="The code multiplies by a weight matrix W before or after aggregation",
            context=unit.raw,
            output=code,
            threshold=0.7,
        )


class TestLossFidelity:
    def test_implements_mse_plus_l2(self, sample_unit_map):
        code = _load("loss.py")
        unit = sample_unit_map["impl:loss"]
        judge(
            criterion=(
                "The code computes mean squared error plus L2 regularisation: "
                "(1/N) sum (y_hat - y)^2 + lambda * ||theta||^2"
            ),
            context=unit.raw,
            output=code,
            threshold=0.7,
        )

    def test_lambda_is_a_parameter(self, sample_unit_map):
        code = _load("loss.py")
        unit = sample_unit_map["impl:loss"]
        judge(
            criterion="lambda (the regularisation weight) is a function parameter, not hardcoded",
            context=unit.raw,
            output=code,
            threshold=0.7,
        )
