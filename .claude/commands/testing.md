# Testing Conventions

Write or review tests for this project following these rules.

## Framework

- Use `pytest` exclusively. No `unittest.TestCase` unless a third-party library forces it.
- Group related tests in classes named `Test<Subject>`. Top-level test functions are fine for single isolated checks.

## Fixtures

- Prefer `pytest` fixtures over setup code inside test functions.
- Place shared fixtures in the nearest `conftest.py` (module-level for unit tests, `tests/integration/conftest.py` for integration tests).
- Scope fixtures explicitly: `function` (default), `module`, or `session` — choose the narrowest scope that avoids redundant setup.
- Fixtures should be small and single-purpose. Compose them rather than building large monolithic fixtures.

## Patching and mocking

- Patch at the **function level using the `@pytest.mark` or `@patch` decorator**, not with a `with patch(...)` context manager inside the test body.
- Always patch at the import site of the consumer, not the definition site.

```python
# correct
@patch("latex_ia.worker.litellm.completion")
def test_something(mock_completion): ...


# wrong — do not do this
def test_something():
    with patch("litellm.completion") as mock_completion:
        ...
```

- For injectable dependencies (functions that accept `_completion=None`), pass a `MagicMock` directly — no patching needed.

## Coverage and quality

- Every new public function must have at least one test covering the happy path.
- Edge cases to always test: empty input, missing file, invalid/unexpected data from external systems (LLM, filesystem).
- Integration tests go in `tests/integration/` and are marked `@pytest.mark.integration`.
- Integration tests must not make real LLM calls. Use injectable `_completion` or a recorded fixture.
- Run `make test` (unit only) before committing. Run `make test-all` before opening a PR.
