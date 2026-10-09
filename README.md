# tex2code

Turn the executable parts of a LaTeX paper into a tested code project,
with each change explained in the researcher's own scientific vocabulary.

> **Status:** Milestone 1 — document model and classification gate.
> No LLM calls yet; `auto` mode is reserved for Milestone 2.

---

## Install

```bash
uv pip install -e ".[dev]"
```

---

## Quick start

```bash
tex2code inspect paper.tex
```

Parses the paper and prints every detected unit with its inferred role,
confidence, and pipeline tier.

---

## Processing modes

The `--mode` flag (`-m`) controls how aggressively units are classified.

| Mode | What it does | LLM cost |
|------|-------------|----------|
| `strict` (default) | Only units wrapped in `\begin{tcprocess}` or `\begin{implement}` enter the pipeline. Everything else is invisible. | none |
| `scan` | Skips the opt-in gate — every parsed unit flows through the rule and keyword classifiers. Good for exploring an unannotated paper. | none |
| `auto` | Full pipeline: ambiguous units that survive rules and keyword scoring are sent to the LLM. | pay-per-unit |

```bash
# Default — opt-in markers only
tex2code inspect paper.tex

# Classify everything without any LLM cost
tex2code inspect paper.tex --mode scan

# Full pipeline (Milestone 2)
tex2code inspect paper.tex --mode auto
```

### Marking content for `strict` mode

Wrap any block you want processed:

```latex
\begin{tcprocess}
  Any environment, equation, or paragraph you want in the pipeline.
\end{tcprocess}
```

Force a block to be treated as an implementable spec:

```latex
\begin{implement}
  \begin{algorithm}…\end{algorithm}
\end{implement}
```

---

## Classification tiers

The pipeline is designed to be cheap by default — each tier is only
reached if the previous one did not produce a confident result.

| Tier | Trigger | Cost |
|------|---------|------|
| -1 | No opt-in marker (`strict` mode only) | free |
| 0 | Hash matches manifest (already processed) | free |
| 1 | Explicit `\begin{implement}` marker | free |
| 2 | Section title / environment name rules | free |
| 3 | Keyword scorer | free |
| 4 | LLM (Milestone 2) | API cost |

---

## Makefile commands

```
make install            Install package + dev deps
make install-all        Install with optional deps (deberta, laya)

make test               Unit tests only (fast)
make test-all           All tests including integration
make test-integration   Integration tests against real papers
make cov                Unit tests with coverage report

make lint               ruff check
make fmt                ruff format
make fix                ruff --fix + format (run automatically on Stop)
make check              lint + unit tests

make inspect FILE=…     Inspect any .tex file
make inspect-attention  Inspect "Attention Is All You Need"
make inspect-vae        Inspect "Auto-Encoding Variational Bayes"
make inspect-sample     Inspect the synthetic sample paper
```

---

## Architecture

See [`DESIGN.md`](DESIGN.md) for the full pipeline, gate tiers, domain
calibration design, and milestone roadmap.
