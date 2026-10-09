.DEFAULT_GOAL := help

# ── install ──────────────────────────────────────────────────────────────────

.PHONY: install
install:  ## Install the package and dev dependencies
	uv pip install -e ".[dev]"

.PHONY: install-all
install-all:  ## Install with all optional deps (deberta, laya)
	uv pip install -e ".[dev,deberta,laya]"

# ── test ─────────────────────────────────────────────────────────────────────

.PHONY: test
test:  ## Run unit tests (fast, no integration, no LLM cost)
	uv run pytest -m "not integration and not eval"

.PHONY: test-all
test-all:  ## Run all tests including integration tests against real papers
	uv run pytest -m "not eval"

.PHONY: test-integration
test-integration:  ## Run only integration tests
	uv run pytest -m integration

.PHONY: eval
eval:  ## Run all evals including LLM-judged (costs money)
	uv run pytest tests/evals/

.PHONY: eval-classifier
eval-classifier:  ## Run classifier accuracy evals only (no LLM cost)
	uv run pytest tests/evals/test_classifier.py -v

.PHONY: cov
cov:  ## Run tests with coverage report
	uv run pytest --cov=src/latex_ia --cov-report=term-missing -m "not integration"

# ── lint / format ─────────────────────────────────────────────────────────────

.PHONY: lint
lint:  ## Check code with ruff
	uv run ruff check .

.PHONY: fmt
fmt:  ## Format code with ruff
	uv run ruff format .

.PHONY: fix
fix:  ## Auto-fix lint issues and format
	uv run ruff check --fix . && uv run ruff format .

.PHONY: check
check: lint test  ## Lint + unit tests (pre-commit sanity check)

# ── cli ───────────────────────────────────────────────────────────────────────

.PHONY: inspect
inspect:  ## Inspect a .tex file: make inspect FILE=examples/attention/ms.tex
	uv run tex2code inspect $(FILE)

# ── examples ─────────────────────────────────────────────────────────────────

.PHONY: inspect-attention
inspect-attention:  ## Inspect the Attention Is All You Need paper
	uv run tex2code inspect examples/attention/ms.tex

.PHONY: inspect-vae
inspect-vae:  ## Inspect the VAE paper
	uv run tex2code inspect examples/vae/iclr14_sva.tex

.PHONY: inspect-sample
inspect-sample:  ## Inspect the synthetic sample paper
	uv run tex2code inspect examples/sample_paper/paper.tex

# ── help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
