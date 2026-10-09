# tex2code

Turns the executable parts of a LaTeX paper into a tested code project, and
explains each change in the researcher's scientific vocabulary.
Full architecture and roadmap: see `DESIGN.md`. Read it before starting work.

## Stack
- Python 3.11+, packaged with `pyproject.toml` (src layout: `src/tex2code/`)
- LaTeX parsing: `pylatexenc` (fall back to `TexSoup` only if needed)
- LLM calls: `litellm` (provider-agnostic; swap model via `profile.json`)
- Structured outputs: Pydantic models (plain library, not PydanticAI framework)
- Upgrade path (Milestone 3+): PydanticAI on top of LiteLLM if multi-agent orchestration is needed
- Tests: `pytest`; lint/format: `ruff`
- Docs: MkDocs + Mermaid

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
- **Small, verifiable steps.** Each milestone item ships with tests and a sample
  in `examples/`.

## Current focus
Milestone 1 in `DESIGN.md`: the document model, with no LLM calls yet.
Start with an example paper in `examples/sample_paper/` that exercises every
unit type and role, then build the parser against it.

## Commands
- `pip install -e ".[dev]"` — install
- `pytest` — run tests
- `ruff check . && ruff format .` — lint/format
- `tex2code inspect <file.tex>` — print the document model (Milestone 1)
