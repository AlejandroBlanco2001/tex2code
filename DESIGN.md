# tex2code — Design

> Working name. Rename freely.

## Vision

Researchers write LaTeX; the project builds itself. The LaTeX document is the
specification, and an agent turns the executable parts of it into a clean,
tested, modern code project — while explaining what it did in the researcher's
own scientific vocabulary.

## Target users and modes

1. **Tutor mode** — for researchers who can't code. They describe a change in
   science terms (or edit the LaTeX); the agent implements it, then explains
   *why* in plain language tied to their equations
   ("θ is now a vector because eq. 3 sums over features").
2. **Background mode** — for researchers who just want it seamless. A watcher
   notices `.tex` changes, the agent updates only the affected code, and asks
   for input only when something is ambiguous or missing.
3. **Onboarding docs** — a living, interactive `docs/` site (glossary,
   diagrams, LaTeX ↔ code map) that helps both newcomers to the repo and the
   agent itself (it's the agent's memory too).

## Architecture

A **headless core** with thin frontends on top, so the UI decision
(Claude Code plugin → VS Code extension → maybe Electron) never forces a rewrite.

```
            ┌──────────────── frontends ────────────────┐
            │ Claude Code plugin │ VS Code ext │ (later) │
            └─────────┬──────────┴──────┬──────┴─────────┘
                      │                 │
                ┌─────▼─────────────────▼─────┐
                │            core             │
                │     (Python, LiteLLM)       │
                └───────────┬─────────────────┘
                            │
               ┌────────────▼────────────┐
               │       watcher loop      │  ← long-running background process
               │  detect → hash → queue  │
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │    processing worker    │
               │ classify → plan → impl  │
               └─────────────────────────┘
```

### Background processing model

`tex2code watch paper.tex` is the **primary UX** — not a one-shot command.
The researcher writes LaTeX; the process runs in the background and reacts to
every save.

```
researcher saves paper.tex
        │
        ▼
file watcher (watchdog) detects change
        │
        ▼
re-parse changed file tree → compute hashes
        │
        ├─ hash unchanged → skip (Tier 0, zero cost)
        │
        └─ hash changed or new unit
                │
                ▼
          build dependency graph → topological sort
                │
                ▼
          process in dependency order:
            resolve glossary → build context → LLM call
            update glossary → write output → update manifest
                │
                ▼
          surface result (terminal / plugin notification)
```

Key properties of this model:

- **Always-on, never blocking.** The researcher keeps writing; code updates
  arrive asynchronously in the background.
- **Incremental by design.** The hash cache (Tier 0) means only changed units
  cost anything. A stable section is processed exactly once in its lifetime.
- **No RAG, no stale index.** The LaTeX file *is* the source of truth. The
  watcher re-parses on every save; the LLM receives fresh content every time.
  There is no vector store to keep in sync.
- **Topological processing order.** Changed units are sorted by their dependency
  graph before processing, so definition and assumption units are always handled
  before the spec units that use their symbols. The LLM never encounters an
  undefined symbol.
- **Symbol glossary injection.** A running glossary maps symbol names to the raw
  LaTeX of their defining units. Before each LLM call the target unit's symbols
  are resolved against the glossary and injected into the prompt — giving the
  model the exact definitions it needs regardless of where they appear in the
  document.
- **Revisor filters questions before surfacing them.** After the worker raises
  open questions, a revisor agent searches the document using tools
  (`search_document`, `get_unit`) and three enriched signals (question
  rephrasing, LaTeX symbol extraction, dep-graph neighbour traversal) to
  answer as many as possible.  Only questions with no relevant information in
  the paper reach `.tex2code/questions.md`.
- **Pending questions, not blocking prompts.** When the revisor cannot resolve
  a question, it is written to `.tex2code/questions.md` and processing
  continues with other units. The researcher answers when convenient; the
  worker picks up on the next save.

### LLM layer

**LiteLLM** is the provider abstraction. Every LLM call in the pipeline goes
through `litellm.completion()` — swapping provider is a one-line config change
in `profile.json`:

```python
# same call, any provider
completion(model="claude-sonnet-4-6", messages=[...])
completion(model="gpt-4o", messages=[...])
completion(model="moonshot/moonshot-v1-8k", messages=[...])  # Kimi
completion(model="ollama/llama3", messages=[...])  # local
```

Structured outputs use **Pydantic models** directly (not PydanticAI) — the
classifier returns a `ClassificationResult`, the planner returns a `Plan`, etc.
The tool loop for the implementer (~30 lines: call LLM → execute tool → feed
result back → repeat) lives in core and is not delegated to a framework.

**Upgrade path:** when the agent loop grows complex enough to need multi-agent
orchestration, dynamic tool discovery, or long-horizon planning, the core can
adopt **PydanticAI** on top of LiteLLM without changing the provider layer or
the Pydantic result models — the migration surface is small.

#### Context window strategy (no RAG)

Each LLM call receives a context built from two complementary sources,
assembled at call time from the parsed document tree — no vector store,
no pre-indexing, no stale index.

```
system:  profile.json (field, tone, education_level, spec_heuristics)

user:    [positional window]
           section title + path  (e.g. "4. Model / 4.2 Encoder")
           ± 3 units around the target in document order

         [glossary injection]
           raw LaTeX of definition/assumption units whose symbols
           appear in the target unit — resolved from the live glossary,
           regardless of where they appear in the document

         target unit (raw LaTeX + label)  ← TARGET
         task: "classify" | "implement" | "explain"
```

**Dependency graph + topological order** ensure the glossary is populated
before it is needed: definition units are always processed before the spec
units that depend on them.  Edges are derived from explicit `\ref` links
and from symbol co-occurrence with known definition units.

This is fresh on every call. Because the watcher only re-calls the LLM when a
unit's hash changes, the cost of always reading from the file is paid at most
once per edit, not once per query.

#### Structured generation — TDD two-pass for spec units

For `spec` units the worker uses **two independent LLM calls** to prevent
circular tests (where the LLM bakes the same arithmetic error into both the
expected value and the implementation):

**Pass 1 — classify + test-first**
```python
# Returns role, confidence, reasoning, test_stub, open_questions.
# code_stub is intentionally absent — tests are the contract.
{
    "role": "spec",
    "confidence": 0.95,
    "reasoning": "...",
    "test_stub": "import numpy as np\ndef test_attention(): ...",
    "open_questions": [],
}
```
The LLM encodes the mathematical spec as pytest tests with expected values
computed from math arithmetic **in the test body**, never by calling the
function under test.

**Pass 2 — implement from tests**
```python
# Receives the test stub as a contract; returns only code_stub.
{"code_stub": "def scaled_dot_product_attention(Q, K, V, d_k): ..."}
```
The implementation must satisfy the tests from pass 1.  Because the two passes
are independent, an arithmetic error in pass 1's expected value will cause a
test failure — the error is visible instead of silently agreed upon.

For non-`spec` units (definition, assumption, result, context), only pass 1
runs. The full `UnitResult` Pydantic model aggregates both passes:

```python
class UnitResult(BaseModel):
    role: Role
    confidence: float
    reasoning: str
    code_stub: str  # from pass 2, empty for non-spec
    test_stub: str  # from pass 1
    open_questions: list[str]
```

### Core pipeline

```
parse → gate → classify → glossary → dependency graph → diff → plan
             → (confirm) → implement → test → explain → update docs
```

Steps 1–5 are **deterministic code**. The LLM is used for ambiguous
classification, planning, implementation and explanation. Keeping this split is
what makes the system predictable for users who can't audit the code.

The **gate** step (between parse and classify) filters what ever reaches the
LLM. It is **opt-in by default**: only content the author explicitly marked with
`\begin{tcprocess}` is considered. Unmarked content is never sent to the LLM.
See §2 (classify) for the full gate tiers.

### 1. Parse into units

Parse with a real LaTeX parser (`pylatexenc` first; `TexSoup` or pandoc JSON AST
as alternatives), following `\input` / `\include`. Split into **units**:

- section / subsection (title + nesting path)
- paragraph
- `equation`, `align` (+ `\label`)
- `algorithm`, `algorithmic`
- `definition`, `assumption`, `theorem`
- tables, figures, `\cite`s

Each unit gets:
- `id` — its `\label`, or a path like `sec:method/para:3`
- `hash` — content hash (normalized whitespace)
- `section_path`, `raw`, `refs` (outgoing `\ref`s), `symbols` (math symbols used)

### 2. Classify roles

| Role         | Examples                                  | Agent behavior                                      |
|--------------|-------------------------------------------|-----------------------------------------------------|
| `context`    | intro, related work, motivation           | Read for goals/vocabulary. **Never implements.**    |
| `definition` | notation, symbols, datasets               | Updates glossary (symbol → variable → type/shape). |
| `assumption` | "we assume X ~ Gaussian"                  | Becomes config value or test condition.            |
| `spec`       | model eqs, loss, algorithm, exp. setup    | **Implemented.**                                    |
| `result`     | tables, "we observe that…"                | Expected outputs / checks.                          |

#### Gate tiers (evaluated in order; first match wins)

| Tier | Check | Action |
|------|-------|--------|
| **−1** | No `\begin{tcprocess}` or `\begin{implement}` marker present | **Skip entirely.** Never reaches the LLM. |
| **0** | Content hash matches the stored hash in `manifest.json` | **Skip (cached).** Already processed, nothing changed. |
| **1** | Explicit markup: `\begin{implement}{name}` or `impl:` label | Role = `spec`, confidence = 1.0. Proceed. |
| **2** | Structural rule: section title matches known pattern | Role assigned by rule (e.g. Introduction → `context`). Proceed only if role is actionable. |
| **3** | Keyword scorer (built-in, zero deps) | Score weighted vocab hits → role + confidence. If confidence ≥ threshold → proceed; else escalate. |
| **4** | LLM classifier | Final arbiter for genuinely ambiguous content. Returns role + confidence. |

**Tier −1 is the primary cost control.** In opt-in mode (the default) every
unmarked paragraph, section, figure, and table is invisible to the pipeline.
The author decides what matters; the agent acts on it.

#### Keyword scorer (Tier 3)

A curated vocabulary list produces a weighted score. No model required.

```
spec signals (+):     "we propose", "we define", "we minimize", "the loss is",
                      "we set", "hyperparameter", "given by eq.", "algorithm",
                      "we train", "we implement", "formally", "let θ be"

context signals (−):  "previous work", "related to", "as shown by [",
                      "in contrast", "survey", "prior art", "has been studied",
                      "in the literature", "we review"

result signals (→):   "we observe", "table X shows", "outperforms",
                      "performance improves", "we report"
```

Score = Σ matched weights over the block's text. Above the confidence threshold
→ role assigned. Below → escalate to Tier 4 (LLM).

Mitigation for mixed-tone sections (e.g. "Prior approaches to this loss…" before
defining a new one): weight tokens by position within the block (last paragraph
counts more) and let `\label` presence break ties.

#### Pluggable classifier interface

The Tier 3 slot accepts any backend implementing:

```python
def classify(text: str, section_title: str) -> tuple[str, float]: ...  # returns (role, confidence)
```

Built-in levels (configured via `profile.json` or `--classifier` flag):

| Level | Backend | Extra dep | Notes |
|-------|---------|-----------|-------|
| `keyword` (default) | Weighted vocab scorer | none | Zero cost, instant, interpretable |
| `deberta` (optional) | `cross-encoder/nli-deberta-v3-small` (~180 MB) | `sentence-transformers` | Zero-shot NLI; better on prose-heavy papers |
| `laya` (optional) | ModernBERT-large encoder, calibrated probs | `laya` | Multi-question per call; best calibration |

Three layers, in priority order:
1. **Explicit markup** (always wins) — `\begin{implement}{name}…\end{implement}`
   or labels prefixed `impl:`.
2. **Structural rules** — Introduction / Related Work / Conclusion → `context`;
   `algorithm` envs and labeled equations under Method → `spec`.
3. **LLM classification** — only after keyword scorer is inconclusive; must
   return `role` + `confidence`.

### 3. Act by confidence

- Explicit spec → implement (in background if enabled).
- Inferred spec, high confidence → **propose** and ask.
- Low confidence or context → no code changes; may feed glossary/README.

Example: an intro saying "we propose a neural network for rainfall prediction"
records the project goal and may suggest a structure — but no model is created
until a spec unit defines one.

### 4. Dependency graph

Resolve `\ref`s and shared symbols into a DAG (loss → model → notation;
experiment → loss + dataset). Implement in topological order. Missing pieces
become questions: "eq. 5 uses σ but I can't find its definition — hyperparameter?"

### 5. Manifest and diffing

`.tex2code/manifest.json` links marked blocks to the code they produced.
Only `\begin{tcprocess}` / `\begin{implement}` blocks have entries — unmarked
content is never recorded.

```json
{
  "impl:loss": {
    "hash": "a91f…",
    "role": "spec",
    "last_processed": "2026-10-08",
    "code": ["src/model/loss.py::cross_entropy_l2"],
    "tests": ["tests/test_loss.py"]
  },
  "bg:attention": {
    "hash": "c34d…",
    "role": "definition",
    "last_processed": "2026-10-08",
    "outputs": ["docs/glossary.md#attention"]
  }
}
```

On re-run: compute hash of each marked block → compare to manifest.
- Hash unchanged → **skip** (Tier 0 gate). Zero LLM cost for stable content.
- Hash changed → re-process block and cascade to its dependents in the DAG.
- New block (no manifest entry) → process fresh.

Changed `spec` → update its code and dependents. Changed `context` → maybe
refresh docs, nothing else. This is what makes background mode safe.

### 6. Implementation conventions

- Every generated function carries a back-reference comment:
  `# spec: impl:loss (paper.tex, eq. 4)`
- Tests derived from the math: shape checks, closed-form/toy cases,
  gradient checks, convergence on synthetic data.
- Modern project layout: `src/` package, `pyproject.toml`, `tests/`, `configs/`.

### 7. Explanations (tutor mode)

After each change, a short explanation that:
- uses the paper's symbols and section names, not programming jargon first
- says *what* changed, *why* (pointing at the equation/assumption), and *how to check it*
- introduces at most one programming concept at a time, defined simply

### 8. Docs output

The agent maintains `docs/` (built with MkDocs + Mermaid):
- `glossary.md` — symbol → variable name → type/shape → file
- `architecture.md` — Mermaid diagram of the pipeline/modules
- `spec-map.md` — each LaTeX label ↔ its code and tests
The agent also reads these back as project memory.

## LaTeX conventions (`tex2code.sty`)

### Opt-in markers

Everything outside a marker is **invisible to the pipeline**. This is the
primary cost-control mechanism.

```latex
\usepackage{tex2code}

% Mark any block for pipeline consideration (role inferred by classifier)
\begin{tcprocess}{bg:attention}
  The attention mechanism computes $\text{softmax}(QK^T/\sqrt{d})V$.
\end{tcprocess}

% Shorthand: mark as spec + trigger code generation (role = spec, confidence = 1.0)
\begin{implement}{loss}
  \mathcal{L}(\theta) = -\sum_i y_i \log \hat y_i + \lambda \|\theta\|^2
\end{implement}

% Explicit exclusion: skip this block even if it is inside a tcprocess region
\tcskip{ ... }

% Other helpers
\tcsymbol{\theta}{theta}{vector, shape (d,)}   % explicit glossary entry
\tcask{Should λ be tuned or fixed?}            % question for the agent/user
```

**Rendering rule:** all `tex2code` environments and commands must be transparent
in a standard LaTeX build — the PDF looks identical with or without the package.
`tcprocess` and `implement` render as plain text/math; `tcskip` renders its
argument normally; `tcask` is suppressed or rendered as a margin note.

### Marker hierarchy

```
\begin{tcprocess}   — process this block; let the classifier assign a role
\begin{implement}   — process this block; role = spec (strongest signal)
\tcskip             — never process this content
```

`implement` is a subtype of `tcprocess` — every `implement` block is implicitly
a `tcprocess` block with `role = spec` hardcoded.

## Domain calibration (`tex2code init`)

Before the main pipeline runs, the agent performs a one-time calibration that
produces `.tex2code/profile.json`. This file is part of the agent's persistent
memory and shapes every subsequent step.

### Step 0a — Auto-inference

Read the paper's title, abstract, `\documentclass` options, journal macros
(`\journal`, `\venue`, known style files like `neurips_2024.sty`), and citation
style to make a first-pass guess at:

- **Field / subfield** (ML, biology, economics, formal math, social science, …)
- **Formalism level** (equation-heavy, algorithm-heavy, table-heavy, prose-heavy)
- **Venue type** (conference proceedings, journal, thesis, preprint)

### Step 0b — Interactive Q&A

The agent asks **4–6 targeted questions**, pre-populated with its inferences so
the user can confirm or correct rather than type from scratch. Questions are
selected based on what was inferred; not every question appears every time.

| Question | Why it matters |
|---|---|
| What field / subfield is this? | Drives `spec_heuristics`: a social-science "Table 2" is a result; a CS "Table 2" may be a hyperparameter grid. |
| What is your **education level**? (undergrad / master's / PhD / postdoc+) | Narrows scope and effort: an undergrad project gets simpler scaffolding and more explanatory comments; a PhD paper may need a full reproducible pipeline. Adjusts explanation depth and how much the agent assumes about the reader. |
| Who is the **primary reader** of the generated code? (you alone / labmates / engineers / public release) | Sets tone: private script vs. production-quality package. |
| Does the paper have a **public repository or prior implementation**? | Avoids re-implementing what already exists; seeds the dependency graph. |
| Are the **proofs** the spec, or do they justify an algorithm you want implemented? *(math-heavy papers only)* | Determines whether theorems become assertions/tests or just doc-comments. |
| Are you comfortable reading Python, or should explanations stay in math/domain terms? | Tutor-mode verbosity and how much programming jargon to introduce. |

### Step 0c — Reference fetching *(stretch, Milestone 4)*

Extract all `\cite` keys → resolve via Semantic Scholar API or arXiv → pull
abstracts → LLM-summarize into a "prior work context" block stored in
`profile.json`. The agent uses this to:

- Borrow vocabulary from referenced papers ("as in Smith et al. 2022…").
- Detect whether cited methods are already open-source (skip reimplementation).
- Pre-populate the glossary with symbols that appear consistently across refs.

### `profile.json` schema

```json
{
  "field": "machine-learning",
  "subfield": "graph neural networks",
  "venue_type": "conference",
  "education_level": "phd",
  "audience": "labmates",
  "code_reader_expertise": "reads-python",
  "proofs_are_spec": false,
  "spec_heuristics": ["algorithms-are-spec", "labeled-equations-are-spec"],
  "tone": "technical-concise",
  "prior_work_context": "…"
}
```

`spec_heuristics` and `tone` are consumed by the classifier (Step 2) and the
explanation generator (Step 7). `education_level` additionally gates how much
scaffolding and how many explanatory comments the implementer generates.

## Roadmap

**Milestone 1 — Document model (no LLM)** ✓ complete
- [x] Parser → units (with `\input` / `\include` resolution)
- [x] Gate: Tier −1 (marker check) + Tier 0 (hash cache)
- [x] Rule-based role classifier (Tier 2) + keyword scorer (Tier 3)
- [x] `--mode` flag: `strict` / `scan` / `auto`
- [x] CLI: `tex2code inspect paper.tex` prints the document model
- [x] Symbol extraction + dependency graph from `\ref`s and symbols
- [x] Symbol glossary (definition/assumption units seed it; injected into prompts)
- [x] Manifest + hash diffing
- [ ] `tex2code.sty`: `tcprocess`, `implement`, `tcskip`, `tcsymbol`, `tcask`

**Milestone 2 — Background watcher + LLM worker** ✓ largely complete
- [x] `tex2code watch paper.tex` — long-running file watcher (watchdog, 300 ms debounce)
- [x] Change detection: re-parse on save, hash-diff, topological sort, process in dep order
- [x] Section-scoped context builder: ±3 units + glossary injection
- [x] `UnitResult` structured output (role + code_stub + test_stub + open_questions)
- [x] TDD worker: pass 1 (classify + test-first), pass 2 (implement from tests)
- [x] Revisor agent: searches document with tools before writing to `questions.md`
- [x] Readable file names: section-path derived for unlabelled equations
- [x] Pending-questions mechanism → `.tex2code/questions.md`
- [x] Domain calibration: auto-inference + interactive Q&A → `profile.json`
- [ ] Explanation generator (tutor mode), tone driven by `profile.json`
- [ ] Cascade-on-change: when a definition unit changes, re-process its dependents

**Milestone 3 — Quality and frontends**
- [ ] Claude Code plugin: skill + subagents + hooks
- [ ] Docs generation (MkDocs + Mermaid): glossary, spec-map, architecture diagram

**Milestone 4 — Later**
- [ ] VS Code extension (side panels: explanations, pending questions, docs)
- [ ] Write results back to LaTeX (`\input` tables/figures from code outputs)
- [ ] Reference fetching: Semantic Scholar / arXiv → prior-work context in `profile.json`
- [ ] Evaluate Electron only if non-coder UX demands it
