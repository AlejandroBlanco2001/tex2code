# Design Sync

Check that the implementation matches what DESIGN.md describes. Find drift before it compounds.

## Steps

1. Read `DESIGN.md` in full.
2. For each concrete claim in DESIGN.md, verify it against the code. Concrete claims are:
   - Named modules, classes, or functions ("the worker calls `litellm.completion`")
   - Data model schemas (field names, types, defaults)
   - Pipeline steps and their order
   - Gate tier numbers and their conditions
   - File paths and directory layout
   - CLI command names and flags
   - Behaviour descriptions ("debounce of 300 ms", "section-scoped context window", "±3 units")

3. Report findings in three buckets:

```
✓  MATCHES      <claim>  →  <where verified>
~  DRIFT        <claim>  →  <what the code actually does>
?  UNVERIFIABLE <claim>  →  <why it can't be checked statically>
```

4. For each DRIFT item, state the fix: either update DESIGN.md to match the code, or update the code to match DESIGN.md. Ask which the user prefers if it is not obvious.

5. Check for things in the code that are **not documented** in DESIGN.md and may deserve a mention (new modules, new behaviour, changed defaults).

## Focus areas

- `models.py` field names vs DESIGN.md schema tables
- Gate tier table in DESIGN.md §2 vs `gate.py`, `rules.py`, `keyword.py`
- Pipeline diagram vs actual call chain in `watcher.py` → `worker.py` → `output.py`
- `UnitResult` fields vs DESIGN.md structured generation section
- `Profile` fields vs DESIGN.md `profile.json` schema
- CLI commands (`inspect`, `watch`, `init`) vs DESIGN.md descriptions
- File layout vs DESIGN.md and `/files` skill layout table
