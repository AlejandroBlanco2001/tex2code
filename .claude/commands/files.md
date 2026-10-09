# File Organisation

Apply these rules when creating or refactoring files in this project.

## Size

- Keep files small. A file that is growing past ~150 lines is a signal to split it.
- One primary responsibility per file. If you need to describe a file's purpose with "and", it should be two files.
- Prefer many small modules over one large module. Import cost is negligible; cognitive cost of a 400-line file is not.

## Splitting a file

When a file needs to be split:
1. Identify the distinct responsibilities (e.g. parsing vs. walking vs. resolving includes).
2. Create one file per responsibility.
3. Re-export from the package `__init__.py` if the public API must stay stable.
4. Update all imports across the codebase.
5. Keep the split in a single commit with a clear message ("refactor: split X into A and B").

## Naming

- Module names are `snake_case`, short, and describe what the module *does* (verb) or *contains* (noun): `context.py`, `worker.py`, `output.py`.
- Avoid generic names: `utils.py`, `helpers.py`, `misc.py`. Name the concept instead.
- Test files mirror source files: `src/latex_ia/worker.py` → `tests/test_worker.py`.

## Project layout

```
src/latex_ia/
  __init__.py          version only
  models.py            shared domain types (keep lean — no logic)
  cli.py               Typer commands only — no business logic
  parser/              one file per parsing concern
  classifier/          one file per classifier tier
  context.py           context window builder
  worker.py            LLM call + response parsing
  output.py            write results to disk
  watcher.py           file watcher event loop
  calibration.py       domain calibration Q&A
  profile.py           profile load/save
  manifest.py          manifest load/save
tests/
  test_<module>.py     mirrors src layout
  integration/         real-paper acceptance tests
```

- `cli.py` must stay thin: parse args, call a function from the appropriate module, print results. No business logic in CLI handlers.
- `models.py` must stay a pure data file: Pydantic models and enums only, no functions with logic.
