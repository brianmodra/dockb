# Markdown-Based Design

## Executive Summary

This document is the design record for making markdown DockB's source of truth. Each chapter is a
markdown file whose text is canonical; the backend rehydrates the knowledge graph from it, and the
file format lays each paragraph out as one identity span holding its sentences one per line, so
paragraph identity survives serialization and line-based git merges stay at sentence granularity.
It records the decisions — drop the editor front end, make the save-and-rehydrate path synchronous,
carry paragraph identity in the format, give the backend ownership of the markdown files and the
git repo, and check syntax in two interactive layers — remark-lint structure lint in the editor and
backend prose/NLP validation, neither part of the save path — and the alternatives that lost to them.

Read this to learn why the format is what it is, how saving rehydrates through the backend, how
validity surfaces interactively as diagnostics anchored to the sentence text, and what is still open
before the design can be trusted. The concrete format and its one implementation live
in `src/dockb/infrastructure/markdown/` and its README; this document is the rationale behind them
and the roadmap for what comes after.

## 1. The problem we were trying to solve

The original front end is a React + Tiptap (ProseMirror) browser editor that talks to a FastAPI
backend over a JSON REST API. Development against ProseMirror was repeatedly difficult. The pain
point was *not* the framework's inability to represent semantics — it was the **bidirectional
async restructure race**: the front end edits a tree, the backend asynchronously tokenizes with
spaCy and splits/merges sentences and paragraphs, then sends a notification that mutates the
tree under the user's cursor.

Investigation also revealed that the backend already had a **git-based markdown snapshot/backup
mechanism** (`src/dockb/infrastructure/history/snapshot_writer.py`, `snapshot_reader.py`) and a set
of **rehydrator services** that rebuild paragraphs, sentences, and tokens from text. These were
written for the API controllers but are reusable as internal components.

## 2. Deciding constraints discovered during investigation

- **iOS/Android are real requirements.** This rules out a terminal SPA (a terminal cannot reach
  phones as a product). The contest is therefore browser vs a cross-platform native (e.g. Flutter).
- **No language/runtime constraint.** Options considered included terminal SPAs (ink, Go, Rust),
  Flutter, and staying on the browser. See **Alternatives considered**.
- **The "semantics" the front end tracks are only the hierarchy** (Document → Chapter → Paragraph
  → Sentence). Token-level semantics (tokens, POS, lemmas) are server-only, computed by spaCy,
  and never appear on the client.

## 3. The key decision: drop the editor front end, make markdown canonical

Instead of building or extending an editor, we make **the markdown file the single source of
truth** and the backend **rehydrates from it** using git to detect and classify changes.

This dissolves the editor-framework problem entirely. Any markdown editor — `vim`, `nano`, VSCode,
Cursor, an off-the-shelf editor — can edit the file. The backend rehydration engine does not care
who writes the file.

### The backend owns the markdown files and the git repo

There is **no separate loop process**. The FastAPI backend owns the markdown chapter files — in a
directory it controls (per-document, `chapter-{id}.md` under an environment-configured base, as the
`DocumentStore` in `src/dockb/infrastructure/document_store/` maps it) — and
the git repo. The only writer of record is the API implementation itself: when the editor saves, it
sends the chapter text to an endpoint, the backend writes the file, rehydrates the graph from it,
and returns the canonical text. The editor is a thin client that never touches a filesystem path,
and all work that touches the knowledge graph (tokenization, sentence/paragraph splitting,
persistence) stays behind the API.

### Synchronous save-and-rehydrate (hard design change, supersedes the async loop below)

**The async working loop described below is replaced.** Its asynchronous nature (file changes
arriving while rehydration runs, discard-and-rerun, cancel-and-rerun job reuse) is **impractical**
and is dropped. From this point on the model is:

**Save → full re-hydration → the editor receives the updates before the user can continue
editing.**

The save is synchronous with re-hydration: the editor is blocked (or the update delivered in-line)
until the knowledge graph is current, so the editor always works against hydrated truth and there is
never stale-client state to reconcile.

Concretely, a save is the editor sending the current text to `PUT /api/chapters/{id}/document`.
The backend writes that text to the chapter file it owns (this is the only place the file on disk
is written by the editor's action — through the API, never by the editor touching the filesystem),
runs `apply_chapter_file()`, canonicalizes, git-snapshots, and returns the canonical span-form text
plus a change summary. Saves to one chapter serialize under a per-chapter lock (last-write-wins
within the queue) because `apply_chapter_file()` reads the file.

Consequences:

- The save path is the **document lifecycle endpoints** (see **New API endpoints** below) wrapping
  `apply_chapter_file()`; the fine-grained rehydrate endpoints (`PUT /api/chapters/{id}/rehydrate`,
  `PUT /api/paragraphs/{id}/rehydrate`, `PUT /api/sentences/{id}/rehydrate`) remain for clients that
  edit via fine-grained CRUD.
- Change detection against the **old** side does **not** re-parse the previous markdown file. The
  previous (hydrated) chapter is read from the **knowledge graph**; the new markdown file is the
  only text parsed. `data-par-id` on spans identifies paragraphs, not sentence content.
- **The editor and file-save mechanics are deferred** (a later feature): the editing UI is out of
  scope today, so the lifecycle endpoints are exercised by tests and any client.

### The working loop (superseded)

1. A file change is detected (e.g. a save).
2. The change is classified from `git diff` (see **How the depth of change is classified**) and the
   appropriate rehydrator is invoked **through the API**.
3. If a *new* file change arrives while rehydration is in progress and it **conflicts**, discard
   the in-flight rehydration and restart on the current file state.
4. On success, merge the hydration output against the current file on disk, detect conflict with
   `git merge-file --diff3 -p`, then `git add` and `git commit`.
5. Conflict detection negative → commit. If rehydration cannot converge after a configurable number
   of consecutive failures, **freeze the editor** so rehydration can complete (a later feature, once
   we own the editor).

This section is retained only as the record of the rejected design. It reuses the
existing cancel-and-rerun job semantics (`Job.cancel()` / `on_cancel()` in
`src/dockb/services/semantics/README.md`), which remain server-side behind the API.

### How the depth of change is classified

`git diff` between the working tree and `HEAD` determines **where** and **how deep** a change is:

- A sentence-level change is a small hunk inside one paragraph.
- A paragraph-level change spans a paragraph block.
- An extensive change requires a whole-chapter rehydrate.

Note: `git diff` tells us the *granularity* (where/how deep), but the *semantic type* of the change
(edit vs split vs merge) is determined by running spaCy at rehydrate time — as it already is today.
The diff is not asked to infer sentence structure; it only scopes the work.

### New API endpoints

The existing API is **fine-grained, already-structured CRUD** (create/update single nodes from
pre-delimited ProseMirror JSON). The backend-owned file model adds a second, whole-file family of
operations — the **document lifecycle**: document create and open, chapter create with explicit
ordering, and a per-chapter document read/save pair (see **Document lifecycle and chapter ordering**
below for the semantics of each).

Each save is a **cascade replace** (delete descendants, then rebuild) in one atomic call that
delegates to the existing `apply_chapter_file()` service; no new rehydration behavior is invented.
The `GET` variants are materializing and reconciling: opening a document/chapter creates the owned
file from the graph when missing, and absorbs any hand edit to the file through the same
`apply_chapter_file()` path before returning canonical text.

Two smaller changes:

- **Per-chapter save lock.** Saves to one chapter serialize under a lock keyed by chapter id
  (last-write-wins within the queue) — `apply_chapter_file()` reads the file, so interleaved saves
  would read and clobber each other. The lock entry is ref-counted and evicted when idle, so the
  registry does not grow over a server's lifetime; waiters always observe the same lock object.
- **Session/auth.** The services are bound to a per-user OAuth `SessionContext` (JobQueue, DocCache).
  The editor authenticates as a user to call the API — a client concern only, no endpoint change.

What does **not** change: `GET /api/notifications` still returns the async split payloads
(`sentence_split` / `paragraph_split`); the synchronous save makes them redundant for the save path,
but they remain available to clients that edit via fine-grained CRUD.

### Git stays with the backend (no loop process)

The git-based **history/versioning** logic — `SnapshotWriter`, `SnapshotReader`, and the git
command work — **stays in the backend**, because the backend owns the markdown files. Each save
writes the canonical `chapter-{id}.md` (the same file `SnapshotWriter` produces) and commits it;
with the backend as the only writer of both the file and the repo there is exactly one owner and no
two-writer conflict to manage.

This leaves a clean split:

- **Backend (owns the files + git + knowledge graph):** writes the canonical file on save, `git add`
  / `git commit` per save, markdown serialization, snapshot listing and restore-from-git, and the
  persistence half of a restore. The editor never touches the filesystem or git.
- **Editor (thin client):** sends raw text and receives canonical text; never reaches into services,
  repositories, the filesystem, or git.

Consequence for the history API:

- `GET /api/history/{chapter_id}` (list commits) **stays on the backend**.
- `PATCH /api/history/{chapter_id}` (restore) **keeps its shape**: the backend reads the commit
  from git and persists it to Neo4j.

### Document lifecycle and chapter ordering

The owned directory tree is the editor's entire world, delivered through the API:

- **Start:** `POST /api/documents` with `{id, title, author}`. The title must be **unique** — an
  exact-title match against the knowledge graph is rejected (409) rather than silently reused. The
  server creates the document's directory and `document_metadata.yaml` (title/author) next to it.
- **Open:** `GET /api/documents/{id}` materializes the tree when missing — the document directory,
  `document_metadata.yaml`, and one `chapter-{id}.md` per chapter serialized from the graph — then
  returns the document. `GET /api/chapters/{id}` does the same for a single chapter file.
- **New chapter:** `POST /api/chapters` with `{id, title, document_id, after_chapter_id}`. The new
  chapter is placed in sequence and the server writes an **empty** `chapter-{id}.md` (front matter
  with `id`/`title`, no body).
- **Save:** `PUT /api/chapters/{id}/document` as described above. The request body is the editor's
  loose text. The server writes it to the owned file, forcing the chapter's `id`/`title` (and its
  `act` when set) into the front matter — the server, not the editor, owns identity — runs
  `apply_chapter_file()`, git-snaps,
  and returns the canonical span-form text plus a change summary (`created`/`changed`/`added`/`deleted`).
- **Open/reconcile:** `GET /api/chapters/{id}/document` materializes the owned file when missing
  (canonical serialization of the graph, git-snapped) and returns the canonical text; when the file
  differs from the last-persisted state (a hand edit), the edit is absorbed through
  `apply_chapter_file()` first, then the canonical text is returned.
- **No store:** without a configured document store (`DOCKB_CHAPTERS_DIR` unset) the
  `.../document` endpoints report the chapter as not found (404).

**Chapter ordering.** Chapters of a document are ordered by the `index` property on their
`PART_OF` relationship to the document (`rc.index` in the document load Cypher). Insertion is
explicit:

- `after_chapter_id` names the chapter the new one goes **after**.
- `after_chapter_id = null` means the new chapter becomes the **first** (index 0). To append, the
  caller passes the currently-last chapter's id — there is no separate "last" sentinel.
- An `after_chapter_id` that is not a chapter of the document is rejected (404).

When a chapter is inserted into the middle, the server renumbers every chapter at or after the
insertion point (a single Cypher increment) so `index` remains 0..n-1 and the listing
(`GET /api/chapters?document=...`, ordered by `index`) matches the assigned sequence.

**Acts.** Acts are not a separate model entity: they are the `act` front-matter attribute persisted
on each chapter (and stored in the graph like the chapter's other attrs). The chapter listing
(`GET /api/chapters?document=...`) carries `act` so the editor can group chapters under act headers.
A chapter moved to a position whose neighbours belong to a different act adopting that act is
decided server-side at the move (reorder) — the editor only sends the order change.

### git branch approach rejected

An earlier variant used git branches: branch, commit the unstaged changes, rehydrate in the
background, merge the branch, resolve conflicts. This was rejected because **conflict resolution
became the product** — an always-on edit-edit merge under an actively-typed cursor. The synchronous
single-truth save path eliminates the merge/conflict-resolver entirely: the latest file always wins.

## 4. The sentence-boundary format rule (settled)

To let `git merge-file` (line-based) resolve at **sentence granularity** rather than paragraph
granularity, hydration normalizes the markdown so that:

- **Paragraph** = a block delimited by a blank line (`\n\n`), written as one
  `<span data-par-id="…">` element wrapping the whole paragraph.
- **Sentence** = one line inside that paragraph span. Each paragraph is written
  as a single span holding its sentences, one per line. Sentences carry no id of
  their own — they are re-derived at hydration time, when spaCy splits the
  paragraph's text, so "Dr."
  and "e.g." are handled correctly there.

The rules, stated symmetrically:

- **The span demarcates the paragraph, not its sentences.** The newlines after
  the open tag and before the close tag are structural, not content; inside the
  span, the sentence-to-sentence newline carries the canonical line layout.
- **A newline mid-sentence is ordinary whitespace.** Renderers treat it as soft
  wrapping; spaCy treats it as whitespace, so the sentence stays intact. A user
  may place a newline mid-sentence freely (it is preserved byte-for-byte).
- **A forced mid-sentence break** is written as `\` followed by a newline
  (CommonMark hard-break syntax). The hydrator must preserve this and not strip
  or reinterpret it.
- **Parse side:** the paragraph text is read from the span — inner text minus
  the structural newlines — and sentences are split from it with spaCy;
  span-free text is split the same way. The per-line layout is a *merge*
  convenience, not a parsing requirement.
- **Write side:** emit one paragraph-span with its sentences one per line;
  span-free content (a `dirty` chapter, a sentence-less paragraph) is wrapped
  raw in a fresh-id span. Sentences are never split at write time.

The one whitespace distinction to keep straight:

| Whitespace | Meaning | For |
|---|---|---|
| Sentence-ender line break | sentence layout (writer-inserted inside the paragraph span) | `git merge-file` granularity |
| Blank line `\n\n` | paragraph boundary | block structure + `git merge-file` |

### Importing files not in this format

A loose chapter file that delimits paragraphs by a **single** newline and runs
its sentences on inside the line imports through the CLI's
`--single-newline-paragraphs` flag: every body line is read as a paragraph block
(span-wrapped paragraphs stay whole), and the write-back produces the canonical
format above, so a second import of the unchanged file detects nothing.

## 5. The concurrency and multi-writer consideration

The markdown editor runs in a different process from the backend, but the backend is the **only
writer of record** for the chapter files, so multi-tasking cannot race the rehydrator the way the
old loop feared. Two kinds of events still interleave with a save:

- **Concurrent saves to one chapter** serialize under the per-chapter lock — `apply_chapter_file()`
  reads the file, so overlapping saves are queued (last-write-wins) rather than run concurrently or
  merged.
- **Hand edits outside the editor/API** are a second, accepted writer. They are not watched; the
  file and the graph simply diverge until the chapter is next **opened**, at which point the
  reconcile-on-open path absorbs the difference through the same `apply_chapter_file()` service
  (synchronously), canonicalizes, snapshots, and returns. Until that open, the graph is stale with
  respect to the hand edit — the accepted staleness window.

### Idempotent, minimal-diff hydration requirement

The scheme depends on rehydration's **write** being **minimal-diff** — it must touch only the
changed paragraph/sentence and preserve the rest byte-for-byte. If hydration rewrote the whole
chapter, every save would rewrite the file and the editor would lose its anchor. **This
minimal-write property is load-bearing and must be verified/guaranteed.**

### Save latency and the freeze

A save is synchronous, so the editor appears frozen for its duration. The freeze is a freeze of
*edits*, not of input: the editor's event loop keeps running, the editor is set read-only, and a
bounded number of further input events are buffered and replayed after the restore (the cursor/view
are recovered by paragraph identity, not byte offset, since the returned canonical text differs
from what the user typed). Keeping the pipeline warm (spaCy model, the per-chapter lock) keeps this
under a second in the common case.

## 6. Sentence metadata in the format

The snapshot writer serializes the hierarchy into markdown and wraps every
paragraph in a `<span data-par-id="…">` element carrying its UUID, holding the
paragraph's sentences one per line. The parser reads the spans
back onto the Paragraph model objects, so paragraph *identity* survives
serialization. Sentences carry no id in the format: they are re-derived at
parse time (spaCy over the span's text, or over span-free text) and are
assigned fresh UUIDs.

The README's aspirational metadata — JSON-in-HTML-comment blobs for non-text
attrs (e.g. premise, elevator pitch) and `<span data-attr>` inline metadata —
remains out of scope; only the paragraph identity spans (`data-par-id`) are
implemented today. They reuse the span mechanism described below for the
later NLP-derived spans.

With the single-truth save path — the backend as the only writer of record — embedding
paragraph-level identity in the format keeps the graph aligned with the file
across rehydration and makes paragraph identity stable for the reconcile
and save-atomicity features to come, at negligible cost.

### Semantic spans inline in the text (pivotal)

Rehydration stops at the sentence level (it does not descend to triples). This coarse granularity
lets the derived semantics — and the NLP views that show them — ride **in the flat markdown itself**
as inline span metadata, rather than as a special rendering layer the editor must overlay. Because
the semantics are *serialized into the text*, a flat markdown editor (CodeMirror, a textarea, or a
future WYSIWYG) can host them: the renderer simply styles/links the spans it already has.

Example (SPO = subject / predicate / object of an extracted triple):

```
The <span data-triple="1" data-spo="subject">NASA team</span>
<span data-triple="1" data-spo="predicate">successfully launched</span> the
<span data-triple="1" data-spo="object">James Webb Telescope</span>, while
<span data-triple="2" data-spo="subject">ESA</span>
<span data-triple="2" data-spo="predicate">closely monitored</span> the
<span data-triple="2" data-spo="object">telemetry data</span>.
```

The same span mechanism carries any NLP-derived attribute — a verb marked as a gerund, a character
name with a link to its description and the other places it appears, over-used words flagged with
suggestions. These are all *rendered attributes of spans already in the text*, not framework overlays.

Consequences and requirements:

- **The normalized markdown is the source of truth for spans.** When rehydration runs spaCy on a
  changed sentence, the resulting triples/roles must be written **back into the markdown as spans**
  (part of the write-side normalization). This is a **format addition**: the current snapshot writer
  emits only the paragraph identity spans, not semantic ones.
- **The FE renders spans; it does not derive them.** Rendering is the only FE responsibility for
  semantics.
- **Granularity is the sentence.** Inline semantic spans sit inside a paragraph's identity span,
  scoped to a sentence (one per line); a sentence split re-derives
  spans per resulting sentence; a merge re-derives across combined text — the same scoped
  rehydration as tokens. No global re-derivation.
- **Version-control friendly.** Inline spans sit on one line, so they do not fight the
  newline-after-sentence line-based merge, and git sees them like any text change.
- **Renderer caveat:** markdown renderers vary in inline-HTML support. Browser `markdown-it`/HTML or
  TipTap handle them; CodeMirror needs a small language tokenizing `data-spo`/`data-*` spans;
  Flutter's `flutter_markdown` does **not** support inline HTML, so a Flutter client needs an
  attr_list/span extension or a custom span parser instead.

This resolves the earlier question of whether we "need a tree-based WYSIWYG framework to show
semantics": we do not, because the semantics live in the text we already control. The flat,
editor-agnostic markdown core stands unchanged; the rich NLP UI becomes a *rendering* concern for
whatever client renders the spans.

## 7. Syntax checking and diagnostics (decided)

A chapter's *syntax* is checked in two layers, both **interactive only**: remark-lint in the editor
for structure, and backend prose/NLP validation for prose. Neither is part of the synchronous save
path (see **Synchronous save-and-rehydrate** above): saves stay a lean canonicalizing
`apply_chapter_file()` pass, and nothing the user does while typing is written to the file, sent
through the save endpoint, or folded into the canonical text. Diagnostics are view-only decorations
of the text as displayed.

### Structure lint in the editor: remark-lint (decided)

The CodeMirror 6 source mode hosts edition-time structure linting with remark-lint. The canonical
format is **not** GFM — paragraph identity and semantics ride in inline HTML spans (`data-par-id`,
`data-spo`), and sentences run one per line — so two remark defaults conflict with it by design and
are **disabled**:

- **`maximum-line-length`** — a sentence is one line, so line length tracks sentence length, not
  hard wrapping; long valid sentences must not be flagged.
- **`no-inline-html`** — inline spans are the format's own identity and semantics mechanism; the
  lint must target the prose *inside* the spans, not reject the spans.

Remaining remark rules run against the paragraph text inside the identity spans. Lint follows the
editor's transaction stream, debounced over keystrokes — it reacts to typing, never to saves, and
never writes to the file or git. Positions map onto the canonical text through the span-aware CM
language extension and render as diagnostics on the sentence text as displayed, in the source mode
and the WYSIWYG view alike. The editor flags; it derives and rewrites nothing.

### Prose and NLP validation in the backend (decided)

Prose/NLP validation is an interactive feature over the same chapter text, computed by the backend:

- spaCy sentence segmentation — the same segmentation hydration applies — keys every diagnostic to
  the originating sentence, so a flag stays attached to its sentence text whichever view displays
  it.
- Diagnostics are delivered over the retained async notifications channel, debounced as the user
  types; they are not part of the save request, the save response, or the canonical text. The
  backend remains the only writer of record and diagnostics never touch files or git.
- The checks are spaCy/proselint assertions on sentence text — unterminated or fragmentary
  sentences, sentence length, terminology consistency, flagged overused words. They are opinions,
  not mutations.

This is deliberately distinct from the canonicalized `data-spo` semantics (see **Semantic spans
inline in the text** above): curated semantics serialize into the file as spans; validation
diagnostics are ephemeral decorations that never reach the file, so the minimal-diff guarantee is
untouched by validation depth.

Consequences:

- Save latency is unaffected by validation depth: both layers run off the save path.
- Sentences are the shared anchor both views project, so diagnostics attach to sentence text *as
  displayed* — inline markers and squiggles on the sentence text, in the WYSIWYG view and the source
  mode alike.
- No new writer of record and no format addition; the save/git/hydration invariants are unchanged.
- A diagnostic that arrives after the text has moved must not point at the wrong sentence; the
  anchoring semantics are listed in **Open questions** below.

## 8. Sequence of implementation

This is the order we expect to build, matching the dependencies above; it is subject to adjustment
during planning.

1. **Document-store foundation:** the owned directory tree (per-document directory, metadata,
   chapter files, path-from-ids safety) and the foundational CRUD behaviors the lifecycle builds on
   (unique document title, chapter ordering). The fine-grained `.../rehydrate` endpoints and the
   `?format=markdown` GET option are retained for CRUD clients, not part of this work.
2. **Synchronous document lifecycle on the backend.** The backend owns the markdown files + git
   repo (no loop process): document create with unique-title check and materialized tree; open a
   document / open a chapter auto-materialize the owned file(s) from the graph; save
   (`PUT /api/chapters/{id}/document`) writes the file, diffs against the chapter read from the
   knowledge graph (changed / new / deleted paragraphs, classified from `data-par-id` identity +
   parsed sentence text), rehydrates synchronously through `apply_chapter_file()`, canonicalizes,
   snapshots, and returns canonical text; open reconciles hand edits to the file (reconcile-on-open),
   accepting a staleness window until then. The former async loop (file-watch,
   `git merge-file --diff3 -p`, cancel-and-rerun) is dropped per **Synchronous save-and-rehydrate**
   above.
   - Enforce the sentence-boundary / minimal-write normalization rules.
   - `SnapshotWriter`/`SnapshotReader` and all git logic stay in the backend (they already live there).
3. **Remove the old front end** (React + Tiptap/ProseMirror) and any backend code only it used.
4. **Editor integration** (later): wires the editor's save into the synchronous rehydrate step,
   and hooks in syntax checking and diagnostics (see **Syntax checking and diagnostics** above): the
   remark-lint config for the span format and the sentence-anchored rendering of backend
   diagnostics, both interactive only. Paragraph identity is already in the format (`data-par-id`
   spans).

### Front-end platform (PC-only variant, decided)

For the **PC-only** target (Linux/macOS/Windows) with a WYSIWYG-primary editor plus a CodeMirror
markdown source mode and the NLP span views: **Electron + TypeScript.** Only Tauri was a serious
alternative; it was rejected because its shell is Rust, which would force the backend machinery
and the editor's sync logic into two languages. Keeping the editor in one Node process means one
language for the whole PC-frontend stack.

Concretely:

- **Editor:** CodeMirror 6 for the markdown source mode; browser markdown rendering / WYSIWYG
  (markdown-it + HTML, or TipTap) for the primary view; the NLP semantics render as styled/clickable
  spans already present in the text (`data-triple` / `data-spo`, etc.). Structure is linted in-editor
  with remark-lint (`maximum-line-length` and `no-inline-html` disabled for the span format); backend
  prose/NLP diagnostics render sentence-anchored in both views. Both layers are interactive only,
  never part of a save. The editor talks to the API
  only — it never touches files, git, services, or repositories.
- **Sync engine (on the backend):** owns the markdown files + git repo, applies
  `apply_chapter_file()` on save, reconciles hand edits on open, snapshots and restores from git.
- **Portability note:** this decision is for PC-only. If mobile/iPad ever becomes a requirement, the
  flat markdown + span format is unchanged and a Flutter client could drive the same backend lifecycle
  via the API; only the editor shell differs.

The editor shell's layout and interactions are specified in `README_markdown_editor_ui.md`.

## 9. Alternatives considered (and why not)

- **Terminal SPA (`ink`, Go bubbletea, Rust ratatui).** Clean for a desktop tool, but **cannot
  reach iOS/Android** — incompatible with the real requirement. Rejected on portability, not on merit.
- **Browser + hand-rolled markdown editor.** Viable (reduces to flat-text→sentence logic), but the
  backend-owned lifecycle makes *any* editor work, so an own-editor is deferred and optional.
- **Flutter + a structure-aware editor (AppFlowy Editor / Super Editor).** A strong rewrite path for a
  native app; its tree model matches our hierarchy. Not chosen as the primary path because the
  file-based rehydration engine is editor-agnostic; Flutter (or any client) could later drive it.
- **Browser + Tiptap/ProseMirror (status quo).** Kept the least new code but did not solve the async
  restructure race; the framework was not the bottleneck, so continuing to invest there was deemed
  lower value than the file-based redesign.
- **git-branch merge scheme.** Rejected; see §3.

## 10. Open questions before trust

These must be settled before/while building, not deferred silently:

1. **Minimal-write guarantee** — confirm the rehydrator writes only the changed region, or make it
   so. This is the load-bearing assumption: it keeps the returned canonical text close to what the
   editor sent, so cursor/view anchors survive a save.
2. **Save latency** — is a synchronous `apply_chapter_file()` pass cheap enough to stay under a
   second for a typical chapter (the spaCy tokenization of changed/new sentences is the floor)?
3. **Reconcile granularity on open** — when a hand edit is absorbed on open, the absorption is
   whole-chapter through `apply_chapter_file()`; confirm the resulting diff touches only the edited
   paragraphs so an unrelated chapter-preserving hand edit does not rewrite surrounding content.
4. **`\` hard-break preservation** — ensure the write-side normalizer never mangles a user's explicit
   backslash-newline.
5. **Span re-derivation on sentence re-split** — confirm how the rehydrator emits/re-emits spans
   when a sentence splits/merges, and that this is scoped and idempotent.
6. **Diagnostic anchoring while typing** — debounced interactive diagnostics arrive after the text
   has moved; define whether stale diagnostics are dropped, re-keyed to the latest segmentation, or
   held until the next pass, so a flag never points at the wrong sentence.
