# tex2code

Turn the executable parts of a LaTeX paper into a tested code project,
with each change explained in the researcher's own scientific vocabulary.

> **Status:** Milestone 2 — background watcher, LLM worker (TDD two-pass),
> revisor agent, dependency graph, symbol glossary, and domain calibration.

---

## Install

```bash
uv pip install -e ".[dev]"
```

---

## Quick start

```bash
# Calibrate once — creates .tex2code/profile.json
tex2code init paper.tex

# Start the background watcher (primary UX)
tex2code watch paper.tex
```

Save any `.tex` file. Changed units are processed automatically: classified,
tested, implemented, and surfaced as reviewed code under `.tex2code/generated/`.

---

## Commands

| Command | What it does |
|---------|-------------|
| `tex2code init paper.tex` | Calibrate domain and create `profile.json` |
| `tex2code watch paper.tex` | Start background watcher; processes changes on save |
| `tex2code watch paper.tex --yes` | Skip the re-init prompt |
| `tex2code inspect paper.tex` | Print document model with inferred roles |
| `tex2code inspect paper.tex --mode auto` | Full pipeline scan (uses LLM) |

---

## How it works

Only content you mark with `\begin{tcprocess}` or `\begin{implement}` enters
the pipeline. Everything else is invisible — zero LLM cost.

```latex
% Mark a block for processing
\begin{tcprocess}
  \begin{equation}
    \mathrm{FFN}(x) = \max(0, xW_1 + b_1)W_2 + b_2
  \end{equation}
\end{tcprocess}

% Force a block to be treated as an implementable spec
\begin{implement}
  \begin{algorithm}…\end{algorithm}
\end{implement}
```

For each marked unit the pipeline:

1. **Classifies** the role (spec, definition, assumption, result, context).
2. **Generates tests first** — expected values computed from the math, independently of any implementation.
3. **Implements** the function so it satisfies those tests (TDD two-pass).
4. **Revises** open questions — a revisor agent searches the document (structured units + prose text) before surfacing anything to you.
5. **Writes** files under `.tex2code/generated/src/` and `.tex2code/generated/tests/`.

---

## Processing modes

The `--mode` flag controls how aggressively units are classified during `inspect`.

| Mode | What it does | LLM cost |
|------|-------------|----------|
| `strict` (default) | Only opt-in marked units enter the pipeline. | none |
| `scan` | Every parsed unit flows through rule and keyword classifiers. | none |
| `auto` | Full pipeline — ambiguous units reach the LLM. | pay-per-unit |

---

## Output layout

```
.tex2code/
  profile.json          # domain calibration
  manifest.json         # unit hashes + file paths
  questions.md          # genuinely unanswerable open questions
  generated/
    src/                # implementation stubs
    tests/              # pytest test stubs
```

---

## Makefile commands

```
make test               Unit tests only (fast)
make test-all           All tests including integration
make fix                ruff lint + format (runs automatically on Stop)
```

---

## Architecture

See [`DESIGN.md`](DESIGN.md) for the full pipeline, gate tiers, domain
calibration design, and milestone roadmap.
