# OpenCode Notes

## Documentaton

Design context is documented in README\*.md files under @src and @tests.

If planning or writing/modifying code (src or tests), the code file's directory and all its
subdirectories down to the root dockb directory, and the associated tests also from the
corresponding test file's directory and all its subdirectories down to the root dockb directory
will sometimes have README\*.md files in them. All of these files are **relevant**.

IMPORTANT: read the **relevant** README\*.md files every time before planning or writing/modifying code or tests.

## Backend Commands
- Install dev deps from repo root: `source .venv/bin/activate && pip install -e '.[dev]'`.
- Backend checks: `source .venv/bin/activate && make` - it runs isort, mypy, pylint, black, ruff, pycycle, and pytest.
- Autofix/format before final checks when editing Python: `black src tests` and `ruff check --fix src tests`.
- Focused tests: e.g. `pytest tests/models/test_documents.py`

## Workflow Procedure
- Use test-driven develppment and focused verification while editing. Write failing tests, then write the code to satisfy those tests. Always **Ask** the user for permission to write code that satisfies the tests. The user will ALWAYS want to review the tests before you proceed.
- After user-approved edits, run `source .venv/bin/activate && make` to run all tests, and linters, and auto reformaters.
- Favor readable, self-describing code over compact code or large explanatory comments.

IMPORTANT: never commit code until it has passed all tests, linting and reformatting.
