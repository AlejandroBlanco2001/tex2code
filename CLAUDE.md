# latex-ia (CLI: `tex2code`)

Turns the executable parts of a LaTeX paper into a tested code project, and
explains each change in the researcher's scientific vocabulary.
Full architecture and roadmap: see `DESIGN.md`. Read it before starting work.

## Stack
- Python 3.14, managed with `uv`; src layout: `src/latex_ia/`
- CLI entry point: `tex2code` (pyproject.toml scripts)
- LaTeX parsing: `pylatexenc` (resolver → walker → helpers pipeline)
- LLM calls: `litellm` (provider-agnostic; swap model via `.tex2code/profile.json`)
- Structured outputs: Pydantic v2 models (plain library, not PydanticAI framework)
- Upgrade path (Milestone 3+): PydanticAI on top of LiteLLM if multi-agent orchestration is needed
- Tests: `pytest`; lint/format: `ruff`
- Docs: MkDocs + Mermaid (Milestone 3)

## Principles
- **Deterministic first.** Parsing, role rules, glossary, dependency graph and
  diffing are plain code with tests. The LLM only handles ambiguous
  classification, planning, implementation and explanation.
- **Opt-in by default.** Only content the author marks with `\begin{tcprocess}`
  or `\begin{implement}` ever enters the pipeline. Unmarked content is invisible.
  This is the primary LLM cost-control mechanism.
- **Hash before calling.** Every marked block is hashed; if the hash matches the
  manifest the block is skipped entirely — zero LLM cost for unchanged content.
- **Cheap classifier before expensive LLM.** Unmarked → keyword scorer → LLM.
  The LLM is the last resort, not the first.
- **Only `spec` units produce code.** Context (intro, related work) never
  triggers implementation.
- **Explicit markup beats inference.** `\begin{implement}` / `impl:` labels
  always win; inferred specs are proposed, not applied.
- **Traceability.** Every generated function has a `# spec: <label>` comment;
  the manifest links units ↔ code ↔ tests.
- **TDD worker.** For spec units, tests are generated first (expected values
  computed from math, independently of the implementation). Code is generated
  in a second pass that must satisfy those tests. Arithmetic errors surface as
  test failures rather than silent circular agreement.
- **Revisor before surfacing questions.** Open questions from the worker are
  checked against the full document by an agent that can search with tools
  before writing to `questions.md`. Only genuinely unanswerable questions reach
  the researcher.
- **Small, verifiable steps.** Each milestone item ships with tests and a sample
  in `examples/`.

## Current focus
Milestone 2 is largely complete. The background watcher, LLM worker (TDD
two-pass), revisor agent, dependency graph, symbol glossary, domain calibration,
and file-naming from section paths are all shipped and tested.

Remaining Milestone 2 items:
- Explanation generator (tutor mode)
- Cascade-on-change: when a definition unit changes, re-process its dependents

Next: Milestone 3 — Claude Code plugin, docs generation (MkDocs + Mermaid).

## Commands
- `uv run pip install -e ".[dev]"` — install in dev mode
- `make test` — run unit tests (excludes integration)
- `make test-all` — run all tests including integration
- `make fix` — ruff lint + format (also runs automatically via Stop hook)
- `uv run tex2code inspect <file.tex>` — print document model with roles
- `uv run tex2code inspect <file.tex> --mode auto` — full pipeline scan
- `uv run tex2code init <file.tex>` — calibrate and create profile.json
- `uv run tex2code watch <file.tex>` — start background watcher (primary UX)
- `uv run tex2code watch <file.tex> --yes` — skip re-init prompt

## Skills (`.claude/commands/`)
- `/conventions` — Python style rules for this project
- `/testing` — test patterns (fixtures, `@patch`, AsyncMock)
- `/files` — file size and responsibility guidelines
- `/milestone` — scan codebase vs DESIGN.md, report done/partial/missing
- `/design-sync` — compare DESIGN.md claims against actual code, flag drift
