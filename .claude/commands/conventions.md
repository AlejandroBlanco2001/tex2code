# Python Conventions

Review or write Python code for this project following these rules. Apply all of them — do not skip any.

## General

- Follow PEP 8 and the Zen of Python (`import this`).
- Explicit is better than implicit: no magic, no clever one-liners that hide intent.
- Always write a docstring for every function and class. One line is fine if that is all it needs; expand only when the why is non-obvious.
- Composition over inheritance. Prefer passing collaborators as arguments or storing them as attributes over subclassing. Avoid deep class hierarchies.

## Async

- If an operation can block (I/O, LLM call, file read/write, network), make it `async` and use `await`. Do not block the event loop.
- Use `asyncio.gather` when independent async tasks can run concurrently.
- The watcher loop and the LLM worker are the primary async boundaries — keep them non-blocking.

## Loops vs comprehensions

- Use a `for` loop when the body has more than one meaningful operation or a side effect.
- Use a comprehension only for simple, single-expression transformations.
- Never nest comprehensions more than one level deep.

## Performance (watchdog path)

- Micro-optimisations on the hot path (file-change detection, hash computation, unit diffing) are acceptable and encouraged.
- Cache compiled regexes at module level (`re.compile` at import time, not inside functions).
- Prefer `set` lookups over `list` scans for membership tests in the classifier.
- Avoid unnecessary object allocation inside the watcher event handler.

## Style

- Imports: stdlib → third-party → local, each group alphabetically sorted.
- No wildcard imports.
- Type-annotate all function signatures. Use `from __future__ import annotations` at the top of every file.
- Prefer `pathlib.Path` over `os.path` for all filesystem operations.
