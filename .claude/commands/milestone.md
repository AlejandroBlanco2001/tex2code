# Milestone Status

Read DESIGN.md and scan the codebase to produce an honest progress report for the current milestone. Do not rely on the checkboxes in DESIGN.md alone — verify each item against the actual code.

## Steps

1. Read `DESIGN.md` and extract every item in the current milestone (the first one with unchecked boxes).
2. For each item, search the codebase to determine its actual status:
   - **Done** — implemented, tested, and working.
   - **Partial** — some code exists but tests are missing, edge cases unhandled, or the feature is stubbed.
   - **Missing** — no implementation found.
3. Print a status table:

```
Milestone N — <title>
─────────────────────────────────────────
✓  done      <item>
~  partial   <item>  → <what's missing>
✗  missing   <item>
```

4. Identify the **single best next task** — the missing or partial item that unblocks the most other work or is closest to completion. State it as a concrete, actionable sentence.

5. If DESIGN.md checkboxes are out of sync with reality, note the discrepancy and offer to update them.

## What to check per item type

- **Parser feature** — look for the relevant env/node type in `latex_parser.py` and a test in `test_parser_robustness.py` or `tests/integration/`.
- **Classifier tier** — look for the tier number in `gate.py`, `rules.py`, or `keyword.py` and a corresponding test.
- **CLI command** — look for `@app.command()` in `cli.py` and a smoke-test or integration test.
- **Data model** — look for the class in `models.py` and tests in `test_models.py`.
- **Background feature** — look for the relevant module (`watcher.py`, `worker.py`, etc.) and its test file.
