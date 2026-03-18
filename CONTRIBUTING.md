# Contributing to twingate-idp-migrator

## Development Setup

Requires Python 3.12+.

```bash
git clone https://github.com/Twingate-Solutions/idp-migrator.git
cd twingate-idp-migrator

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt
```

## Running Tests

```bash
pytest tests/ -v
```

Tests use `pytest-asyncio` (auto mode) and `pytest-httpx` for mocked HTTP. No Twingate API credentials are required.

On Linux, set `QT_QPA_PLATFORM=offscreen` if you see Qt platform plugin errors:

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ -v
```

## Linting

```bash
ruff check src/ tests/
```

To auto-fix most issues:

```bash
ruff check --fix src/ tests/
```

## Type Checking

```bash
mypy src/
```

Strict mode is enabled for `src/api/`, `src/core/`, `src/models.py`, and `src/utils/`. The `src/ui/` layer is excluded from strict checking due to PySide6 signal/slot typing complexity.

## Building a Binary

```bash
pyinstaller migrator.spec
```

Output: `dist/twingate-idp-migrator` (or `dist/twingate-idp-migrator.exe` on Windows).

## Project Structure

```text
src/
  api/         — TwingateClient (httpx async GraphQL)
  core/        — matcher, planner, executor, rollback, changelog
  ui/          — PySide6 wizard pages and QThread workers
  utils/       — structlog setup
  models.py    — Pydantic v2 data models
  main.py      — QApplication entrypoint
tests/         — pytest test suite (no Qt required)
docs/          — technical spec and session plans
```

## Key Design Rules

1. **Mandatory dry run** — never skip the preview step
2. **Never persist credentials** — API key stays in memory only
3. **Additive only** — never remove existing group access during migration
4. **Changelog everything** — every mutation is logged for rollback

See the source code in `src/` and the inline docstrings for implementation details.

## Pull Requests

- Open an issue first for significant changes
- Keep PRs focused — one feature or fix per PR
- All CI checks must pass (ruff, mypy, pytest)
- Follow the code style: Python 3.12+, Pydantic v2, structlog, httpx, PySide6
