# Command-line interfaces

## Executive Summary

These are DockB's three shell commands, all reached through one ``dockb`` command. Two work on chapter files: one walks a folder of markdown and updates the knowledge graph (act chapters line up by the number in their file name, while character chapters need no number), the other writes one chapter back out as markdown, either into the server's folder or to a path you name. The third, `users`, administers accounts — and because there is no self-registration and no password recovery over HTTP, it is the only way to create an account or to get someone back into a lost one.

Use the chapter commands when you need to load an existing manuscript, or rebuild a chapter file, without opening the editor. Use `users` to create, reset, block, or delete an account. All three read the same database settings as the API server.

## Missing settings

The two chapter commands need `NEO4J_URL`, `NEO4J_USER`, and `NEO4J_PASSWORD` — from the environment or a
`.env` file — and the `en_core_web_sm` spaCy model. A variable that is absent or set to an empty
string, or a model that is not installed, is reported as a single `error:` line naming what is
missing, and the command exits 1. Nothing is opened or imported first, so a misconfigured shell
never reaches the database. `startup.py` owns that check for both commands; only a model that is
installed but broken is left to raise, since that is a real fault rather than a missing setting.

## Import a document directory

`dockb import-document <document_dir> [--single-newline-paragraphs]` walks a
directory of markdown chapter files, diffing each against its chapter in the graph and persisting
changes. Each chapter file is matched through its front-matter `id`; changed or new files are
rewritten into the canonical span format (one identity span per paragraph). With
`--single-newline-paragraphs` each body line is read as a paragraph — for files whose paragraphs end
in a single newline and whose sentences run on inside a line — while the write-back stays canonical.
Chapters live only inside top-level `Act <name>` subdirectories — the act's name is its number
(digits, Roman numerals, or the Unicode single-character numerals), which orders the acts, with the
`Act None` directory holding the act-less chapters first — or in the reserved `Characters`
directory, imported last with no act and category `Character`. Root-level files and directories not
named `Act <name>` (and not named `Characters`) hold no chapters and are skipped. A chapter file's
act derives from its containing directory (used verbatim), which wins over any front-matter `act`;
a `Characters` file's category likewise wins over the front matter. The canonical write-back adds
the chapter's `category` to the front matter. Within an act each
file is imported in the order of the sequence number in its name — trailing at the end or embedded
between spaces — with at most one letter (5, 5a, 5b, 6; "Bad Guys Close In 48 Jael" → 48), and an
act file's name must carry that number. `Characters` files need no number: they import by file
name, and numbers in their names (or duplicated across them) are ignored. A file
that is not numbered in an act, two acts numbering the same, or two act files in one act
numbering the same abort the import. See
`../infrastructure/changes/README.md` for the diffing behavior.

## Administer accounts

`dockb users <command>` is the admin-only account tool. It resolves
`DOCKB_CHAPTERS_DIR` through the server's own `resolve_document_base_dir`, so it cannot end up
administering a different database than the one serving requests, and it requires
`DOCKB_SECRET_KEY` — a store keyed with a different secret could not verify a password it wrote.
A missing or blank variable is reported as one `error:` line naming it, and the command exits 1.

| Command | Effect |
| --- | --- |
| `create --username <name> --email <address> [--display-name <name>]` | Generates a temporary password, prints it once, sets `must_change_password`. |
| `list` | Every account with its state, including soft-deleted ones. Never prints a password or a hash. |
| `set-password <username>` | Re-issues a temporary password and re-arms `must_change_password`. |
| `block <username>` / `unblock <username>` | Refuse logins and end live sessions, or reverse it. |
| `delete <username> --yes` | Soft delete: refuses logins, ends sessions, keeps the row. |
| `undelete <username>` | Clears the soft delete, leaving the credentials alone. |

Two conventions the commands hold to:

- **No command takes a password as an argument.** An argument is recorded in the shell history and
  the process table, so the password is generated, printed once on stdout, and never logged. There is
  no way to supply your own: an administrator who wants a person's first password to be something
  specific has them sign in on the generated one and change it.
- **A generated password skips the 12-character minimum.** Its strength comes from `secrets`, not
  from somebody choosing it, and the first thing its holder does is replace it with one they chose.
  The maximum still applies.

`--yes` is required on `delete` because it is the one command whose effect cannot be undone by
running its own name again. `undelete` is deliberate: a soft delete keeps the row, so the username
stays taken and a create reports which deleted account holds it. It stamps
`credentials_changed_at` but touches nothing else, so a session issued before the delete does not
come back with the account.

**Exit codes** are the usual Unix split: `2` for a malformed command line (argparse), `1` for a
command that ran and refused. Every refusal is one `error:` line on stderr, never a traceback.

None of these commands reach into a running server. `block`, `delete`, `set-password` and `undelete`
end a live session by stamping `credentials_changed_at`, which the server compares on its next
request — this process cannot evict an in-memory session it does not own. See
`../../../README_auth.md` §7 for the reasoning.

## Reconstruct a chapter

`dockb reconstruct-chapter <chapter_id> [--out PATH]` renders the chapter with
`chapter_id` from the knowledge graph as markdown. Without `--out` the canonical chapter file is
written into the server-owned tree — `<base>/<document title>/<Act X>/<chapter title>.md`, or
`<base>/<document title>/Characters/<chapter title>.md` for a `Character` chapter — under
`DOCKB_CHAPTERS_DIR` (defaulting to `cwd/dockb_chapters_dir`) — and git-committed; the written path
is printed. With `--out` it is written to the exact `PATH` instead, without touching the store tree.
A chapter id the graph does not know — or a chapter with no owning document (so it cannot be placed) —
prints the error message to stderr and exits non-zero. The serialization itself is the shared format
owned by `../infrastructure/markdown/`.

Every command is also a module, so `python -m dockb.cli.users` remains an equivalent
spelling of `dockb users`. Both run the same `main`, so the two cannot drift apart.
