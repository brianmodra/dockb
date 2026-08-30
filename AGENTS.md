# AGENTS.md — DockB Project Workflow

## Backend Commands
- Install dev deps from repo root: `source .venv/bin/activate && pip install -e '.[dev]'`.
- Backend checks: `source .venv/bin/activate && make` — it runs isort, mypy, pylint, black, ruff, pycycle, and pytest.
- Autofix/format before final checks when editing Python: `black src tests` and `ruff check --fix src tests`.
- Focused tests: e.g. `pytest tests/models/test_documents.py`

## Frontend Commands
- Lint: `cd frontend && npm run lint`
- Type-check + build: `cd frontend && npm run build`
- Tests: `cd frontend && npm test`
- Dev server: `cd frontend && npm run dev` (serves on :3000, proxies /api to :8000)

## Core principles

- **Ask** the user when requirements are unclear or need exploration.
- **Always use Test-Driven Development** (see the Workflow below).
- Prefer **small, focused diffs** and match the patterns of the package you touch.

## Docs & READMEs

- Start with the root [`README.md`](README.md). Package READMEs may be incomplete or stale —
  confirm against the code.
- READMEs hold the design context and the spec. The **relevant** READMEs for any code file are
  the `README*.md` files in that file's directory and every parent directory up to the root — and
  likewise for the corresponding test file's directory chain.
- **Read the relevant READMEs before planning or writing/modifying any code or test.**
- **Keep the relevant READMEs up to date** as you add features or fix bugs. Not every directory
  needs one, as long as a README higher in the tree adequately explains the code beneath it. Add
  `README*.md` files where coverage is missing; a directory may hold several named by topic (e.g.
  `README_API.md`, `README_editing.md`). If you restructure a directory tree, re-home the affected
  documentation into new READMEs.

## Workflow

### 1. Understand the request

The user may type a prompt directly, point you at a markdown file, or reference a Jira ticket.
Establish what is being built or fixed before planning.

### 2. Plan

- Build the plan from the spec and further discussion with the user.
- **Ask** the user how to break the build into sections, suggesting a breakdown where each section
  (and its PR) is small. Write the agreed breakdown into the plan.
- **Do not start the build until the user has re-read and approved the plan, including the
  breakdown.** The build may be a single section or a cycle of several.

### 3. Build — the TDD loop

Before starting the first section, **Ask** if the user is ready to proceed. Then work through each
section of the breakdown, using this sequence:

1. **README first.** Create or update the relevant `README*.md` files to reflect the design.
2. **Skeletons.** Write the class/module skeletons.
3. **Failing tests.** Write the tests; they should fail at this point.
4. **Review gate.** **Ask** the user to review the README(s), skeletons, and failing tests. Do not
   continue until they approve.
5. **Implement.** Write the code so the tests pass.
   Favor readable, self-describing code over compact code or large explanatory comments.
6. **Lint, test, fix.** Run linting and the tests; fix anything that fails.
   run `source .venv/bin/activate && make` to run all tests, and linters, and auto reformaters.


A single build section may contain multiple TDD cycles.

If the user requests changes during or after coding, reflect them in the plan and, where they
affect the spec, in the relevant READMEs.

### 4. Wrap up the section

1. **Code review.**
   #### Based on: code-review hook from Claude
   #### License: Apache License 2.0 (http://www.apache.org/licenses/LICENSE-2.0)

   To do this, follow these steps precisely:
   a. Audit the changes to make sure they comply with the AGENTS.md.
   b. Do a shallow scan for obvious bugs. Avoid reading extra context beyond the changes, focusing just on the changes themselves.
      Focus on large bugs, and avoid small issues and nitpicks. Ignore likely false positives.
   c. Read code comments in the modified files, and make sure the changes comply with any guidance in the comments.

   For each issue found, score it to indicate the level of confidence for whether the issue is real or false positive.
   Score each issue on a scale from 0–100:

   - **0**: False positive — doesn't stand up to light scrutiny, or is a pre-existing issue.
   - **25**: Somewhat confident — might be real, but may also be a false positive. Not verified.
   - **50**: Moderately confident — verified as real, but a nitpick or rare in practice. Low relative importance.
   - **75**: Highly confident — double-checked, very likely real, directly impacts functionality.
   - **100**: Absolutely certain — confirmed real, will happen frequently. Evidence directly confirms this.

   Filter out any issues with a score less than 80. If there are no issues that meet this criterion, do not proceed.

   Finally, comment back to the user:
   - Keep your output brief
   - Avoid emojis
   - Link and cite relevant code, files, and URLs

   Examples of false positives:
   - Pre-existing issues
   - Something that looks like a bug but is not actually a bug
   - Pedantic nitpicks that a senior engineer wouldn't call out
   - Issues that a linter, typechecker, or compiler would catch
     (eg. missing or incorrect imports, type errors, broken tests, formatting issues, pedantic style issues like newlines).
     No need to run these build steps yourself.
   - Changes in functionality that are likely intentional or are directly related to the broader change

   Notes:
   - Do not check build signal or attempt to build or typecheck the app. These will run separately, and are not relevant to your code review.

2. **Security review.**
   Use the file `security-review.md`. Run it against the diff of the changes just made.
   Report any findings directly to the user.

Then repeat the sequence for the next section. Once a PR has been code-reviewed and merged (which
may not happen in order), prune its branch; leave unmerged branches in place.
