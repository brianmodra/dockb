# AGENTS.md — DockB Project Workflow

## Commands

- **"start work"** / **"start-work"** — begin the [Workflow](#workflow) section, from
  A. Understand the request through E. Wrap-up. Do not run any other workflow or skill.
- **"tdd"** / **"TDD"** — begin the [C. Build — the TDD loop](#c-build--the-tdd-loop) section,
  working on the next uncompleted section of the plan breakdown stored at
  `~/.cache/dockb/plan.md`. If that file is missing or stale, ask the user rather than guessing.
- **"wrap up"** / **"wrap-up"** — begin the [E. Wrap-up](#e-wrap-up) section.

## Backend Commands
- Install dev deps from repo root: `source .venv/bin/activate && pip install -e '.[dev]'`.
- Backend checks: `source .venv/bin/activate && make` — it runs ruff (import sort + lint), mypy, pylint, black, pycycle, and pytest.
- When editing Python code, autofix/format and check via `make`; do not call black or ruff directly.
- Backend dev server: from `src/`, `source ../.venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`. Requires the `NEO4J_URL`, `NEO4J_USER`, and `NEO4J_PASSWORD` environment variables (`.env` in the repo root, or exported).
- Focused tests: e.g. `pytest tests/dockb/models/test_document.py`.

## Frontend Commands
- Lint: `cd frontend && npm run lint`
- Type-check + build: `cd frontend && npm run build`
- Tests: `cd frontend && npm test`
- Dev server: `cd frontend && npm run dev` (serves on :3000, proxies /api to :8000)

## Core principles

- **Ask** the user when requirements are unclear or need exploration.
- **Always use Test-Driven Development** (see the Workflow below).
- Never use tools, skills, or any files under `/home/brian-modra/.claude`.
- Prefer **small, focused diffs** and match the patterns of the package you touch.

## Specification

- `README*.md` files hold the design context and the specification.
- The root [`README.md`](README.md) points to the install command; the whole-project specification lives in [`README.md`](README.md).
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

When the user tells you to "start work", that means to start with this workflow.

Follow the following alphabetical steps exactly and each time you move to the next step,
report to the user which step you are working on. If the step contains a numbered list,
then report the letter and the number, e.g. "C.3".

After completing a step, and before moving on to the next, present a short summary
to the user.

### A. Understand the request

The user may type a prompt directly, point you at a markdown file, or reference a Jira ticket.
Establish what is being built or fixed before planning.

### B. Plan

- Build the plan from the spec and further discussion with the user.
- Break the build into sections according to function, so that each section is small
  and all changes in the section stay in the same logical context.
- **Ask** the user to approve the plan. If not approved, discuss with the user.
- Keep the plan and the breakdown in working memory for this session, and persist it to
  `~/.cache/dockb/plan.md` (keyed by working directory) so a later "tdd" can resume it.
  Do not create a plan document inside the repo.
- **Do not start the build until the user has re-read and approved the plan, including the
  breakdown.** The build may be a single section or a cycle of several sections.

### C. Build — the TDD loop

#### False positive

Following are examples of what is meant by a "False Positive":

- Something that looks like a bug but is not actually a bug
- Pedantic nitpicks that a senior engineer wouldn't call out
- Issues that a linter, typechecker, or compiler would catch (e.g. missing or incorrect imports, type errors,
  broken tests, formatting issues, pedantic style issues like newlines).
  Don't flag these as review findings; the lint/test step in the build already surfaces them.
- Changes in functionality that are likely intentional or are directly related to the broader change

#### How to score issues

- Give an issue a score of 0 if you are not confident about it at all.
  This is a [False positive](#false-positive) that doesn't stand up to light scrutiny.
- Give an issue a score of 1 if you are somewhat confident.
  This might be a real issue, but may also be a false positive.
  Leave it alone; mention it to the user only if notable.
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

Follow the following numbered steps exactly and each time you move to the next step,
report to the user which step you are working on, and for which section of the breakdown.
E.g. "Working on step C.4 for section 2."

After completing a step, and before moving on to the next, present a short summary
to the user.

1. **Revisit the specification first.** Review the [Specification](#specification).
   Check for:
   - ambiguity,
   - inconsistency,
   - contradictions,
   - unnecessary repetitions,
   - gaps and unanswered questions,
   - claims that a test could not catch,
   Fix what obviously needs fixing, and **ask** where you need a decision to be made,
   then fix that also.
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
   Run `source .venv/bin/activate && make` to run all backend tests, linters, and auto-reformatters,
   then run the frontend checks (`npm run lint`, `npm run build`, `npm test`).
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
8. **Reflect*** if changes were made to the [Specification](#specification) during steps
   1-7 above, reflect them in the specification by editing the relevant `README*.md` files.

9. **Commit** Git add the unstaged changes, and create a quick summary of the work
   completed in this section and use it as the commit message.
   - This will be limited to one sentence.
   - Use domain words to say what it is for. (Not the mechanism or other details.)
   - Use present tense, verb first, no subject.
   Commit the changes.
   After the commit, pause for [D. Loop](#d-loop). Do **not** offer [E. Wrap-up](#e-wrap-up)
   until every section of the breakdown is complete.

### D. Loop

A single build section may contain multiple TDD sections.

If there are multiple sections, and not all sections are completed after C.9, then
**ask** the user permission to repeat the tdd sequence (C) for the next section. Do not
mention [E. Wrap-up](#e-wrap-up) while sections remain.
Otherwise, if all sections are complete, **ask** the user permission to proceed to wrap-up (E).

### E. Wrap-up

**Consolidate the specification**

Follow the following numbered steps exactly and each time you move to the next step,
report to the user which step you are working on.

1. Compare the [Specification](#specification) to the code. The code should re-state everything
   that is in the specification, in code rather than in English.
   Remove anything in the READMEs that is adequately re-stated in the code.

2. Executive Summary for each relevant `README*.md` file touched in this work:
   (An executive summary will use simple language, to the point, aimed at someone who is not familiar with the work.
   It will describe the reason for the document and what it achieves.
   It should be no more than two paragraphs.
   It will come under a heading "Executive Summary", and will be at the top of the file.)
   Read the entire file, and generate a new summary.
   If the file already has an "Executive Summary" section — wherever it sits in the file —
   replace it, and place the new one at the top.

3. **Ask** the user if the changes committed should be pushed to git.
