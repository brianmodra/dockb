# AGENTS.md — DockB Project Workflow

## Backend Commands
- Install dev deps from repo root: `source .venv/bin/activate && pip install -e '.[dev]'`.
- Backend checks: `source .venv/bin/activate && make` — it runs isort, mypy, pylint, black, ruff, pycycle, and pytest.
- Autofix/format before final checks when editing Python: `black src tests` and `ruff check --fix src tests`.
- Focused tests: e.g. `pytest tests/models/test_documents.py`.

## Frontend Commands
- Lint: `cd frontend && npm run lint`
- Type-check + build: `cd frontend && npm run build`
- Tests: `cd frontend && npm test`
- Dev server: `cd frontend && npm run dev` (serves on :3000, proxies /api to :8000)

## Core principles

- **Ask** the user when requirements are unclear or need exploration.
- **Always use Test-Driven Development** (see the Workflow below).
- Prefer **small, focused diffs** and match the patterns of the package you touch.

## Specification

- `README*.md` files hold the design context and the specification.
- The root [`README.md`](README.md) describes the whole project.
- The **relevant** `README*.md` files for any part of the code are the `README*.md` files in the
  same directory as the code, and every parent directory up to the root — and
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
- Break the build into sections according to function, so that each section is small
  and all changes in the section stay in the same logical context.
- **Ask** the user to approve the plan. If not approved, discuss with the user.
- Write the agreed breakdown into the plan.
- **Do not start the build until the user has re-read and approved the plan, including the
  breakdown.** The build may be a single section or a cycle of several sections.

### 3. Build — the TDD loop

#### False positive

Following are examples of what is meant by a "False Positive":

- Something that looks like a bug but is not actually a bug
- Pedantic nitpicks that a senior engineer wouldn't call out
- Issues that a linter, typechecker, or compiler would catch (e.g. missing or incorrect imports, type errors,
  broken tests, formatting issues, pedantic style issues like newlines).
  No need to run these checks yourself.
- Changes in functionality that are likely intentional or are directly related to the broader change

#### How to score issues

- Give an issue a score of 0 if you are not confident about it at all.
  This is a [False positive](#false-positive) that doesn't stand up to light scrutiny.
- Give an issue a score of 1 if you are somewhat confident.
  This might be a real issue, but may also be a false positive.
- Give an issue a score of 2 if you are moderately confident.
  It is verified as a real issue, but it might be a nitpick or not happen very often.
  Relative to the rest of the issues, it's not very important.
- Give an issue a score of 3 if you are highly confident.
  You double checked the issue and verified that it is very likely a real issue that
  will be hit in practice. The existing approach in the changes is insufficient. The issue is important
  and will directly impact the code's functionality.
- Give an issue a score of 4 if you are absolutely certain about it.
  After double checking the issue, it was confirmed that it is definitely a real issue
  that will happen frequently in practice. The evidence directly confirms this.

#### Work through each section of the breakdown, using this sequence:

1. **README first.** Create or update the relevant `README*.md` files to reflect the design.
2. **Skeletons.** Write the class/module skeletons.
3. **Failing tests.** Write the tests; they should fail at this point.
4. **Review.** Note that a misreading of the [Specification](#specification) propagates into
   the skeletons and the tests. In this review step do not look for bugs, style or duplication.
   Read the [Specification](#specification) again and treat the tests with suspicion.
   For each claim in the specification, ask what implementation would satisfy every test in
   this suite and still break this claim?
   Make additional tests as required, and fix tests as required.
   Notify the user about anything you had to fix or add.
5. **Implement.** Write the code so the tests pass.
   Favor readable, self-describing code over compact code or large explanatory comments.
6. **Lint, test, fix.** Run linting and the tests; fix anything that fails.
   Run `source .venv/bin/activate && make` to run all tests, linters, and auto-reformatters.
7. **Code Review**
   a. Find all the unstaged changes and review them in context with the [Specification](#specification).
   b. Do a shallow scan for obvious bugs. Avoid reading extra context beyond the changes.
   c. Look for SQL injection, command injection, XXE injection, template injection,
      NoSQL injection, path traversal.
   d. Look for authentication bypass, privilege escalation, session management flaws,
      JWT token vulnerabilities, authorization logic bypasses.
   e. Look for hardcoded API keys/passwords/tokens, weak cryptographic algorithms or implementations,
      improper key storage/management, cryptographic randomness issues, certificate validation bypasses.
   f. Look for remote code execution via deserialization, pickle injection, YAML deserialization,
      eval injection in dynamic code execution, XSS (reflected, stored, DOM-based).
   g. Look for sensitive data logging or storage, PII handling violations, API endpoint data leakage,
      debug information exposure.
   h. Score each issue found in a-g according to [How to score issues](#how-to-score-issues).
   i. Fix every issue that scored 3 or 4.
      After fixing, tell the user about these and what you did to fix them.
   j. **Ask** the user about any issues that scored 2, whether to fix or not, and if so, how you would fix.

A single build section may contain multiple TDD cycles.

If changes are made during or after coding, reflect them in the plan and, where they
affect the specification, in the relevant READMEs.

Then repeat the sequence for the next section. Once a PR has been code-reviewed and merged (which
may not happen in order), prune its branch; leave unmerged branches in place.
