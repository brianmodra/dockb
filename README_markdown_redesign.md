# Markdown-Based Design

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

### The working loop is a separate process calling the API

The working loop is **its own process**, distinct from both the markdown editor and the FastAPI
backend. It owns the markdown files and the git repo, and it drives the backend by calling the
**existing REST API**, which gets a small number of **new endpoints** (see **New API endpoints**
below). All work that touches the knowledge graph (tokenization, sentence/paragraph splitting,
persistence) stays behind the API; the loop is a dumb-but-careful client that never reaches into the
services or repositories directly.

### Synchronous save-and-rehydrate (hard design change, supersedes the async loop below)

**The async working loop described below is replaced.** Its asynchronous nature (file changes
arriving while rehydration runs, discard-and-rerun, cancel-and-rerun job reuse) is **impractical**
and is dropped. From this point on the model is:

**Save → full re-hydration → the editor receives the updates before the user can continue
editing.**

The save is synchronous with re-hydration: the editor is blocked (or the update delivered in-line)
until the knowledge graph is current, so the editor always works against hydrated truth and there is
never stale-client state to reconcile.

Consequences:

- The rehydrate endpoints (`PUT /api/chapters/{id}/rehydrate`,
  `PUT /api/paragraphs/{id}/rehydrate`, `PUT /api/sentences/{id}/rehydrate`) are **all kept**; the
  design may iterate and whole-chapter or single-sentence rehydration remain needed.
- Change detection against the **old** side does **not** re-parse the previous markdown file. The
  previous (hydrated) chapter is read from the **knowledge graph**; the new markdown file is the
  only text parsed. `data-par-id` on spans identifies paragraphs, not sentence content.
- **The editor and file-save mechanics are deferred** (a later feature).

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
pre-delimited ProseMirror JSON). The loop's fundamental operation is different: **replace a whole
unit from raw markdown text.** This mismatch is the bulk of the API work. We add a family of
rehydrate-from-text endpoints:

```
PUT /api/chapters/{id}/rehydrate     # body = raw markdown text → rebuild paragraphs+sentences+tokens
PUT /api/paragraphs/{id}/rehydrate   # body = raw text → sentence split + tokens
PUT /api/sentences/{id}/rehydrate    # body = text → re-tokenize only
```

Each folds a **cascade replace** (delete descendants, then rebuild) into one atomic call and enqueues
the DeleteJob/ReconstructJob flow — the same logic the bulk-import hydrators already perform
internally, now exposed as an endpoint. These delegate to the existing hydrators/services; no new
behavior is invented.

Two smaller changes:

- **Read-back for the git merge.** The loop needs the *normalized markdown* (newline-after-sentence)
  of the hydration result to diff3 against the file. Add an optional `?format=markdown` to the
  existing `GET /api/chapters/{id}` (and siblings) so normalization lives in one place instead of
  being duplicated in the loop.
- **Session/auth.** The services are bound to a per-user OAuth `SessionContext` (JobQueue, DocCache).
  The loop process authenticates as a user to call the API — a client concern only, no endpoint
  change. The loop relies on that session's cancel-and-rerun semantics for discard-and-restart.

What does **not** change: `GET /api/notifications` already returns the async split payloads
(`sentence_split` / `paragraph_split`), which the loop consumes and merges back into the file.

### Moving history (git) to the loop process

The git-based **history/versioning** logic — `SnapshotWriter`, `SnapshotReader`, and any git
command work — is moved **out of the main service and into the loop process**, because the
as-yet-to-be-created markdown editing UI will use it directly. `SnapshotWriter`/`SnapshotReader` are
pure filesystem + git + markdown with no backend dependency (the `Chapter` import is only taken for
attribute access), so they move cleanly; in a non-Python loop they are a trivial reimplementation.

This leaves a clean split:

- **Loop process (owns the git repo):** file-watch, `git diff` classification, `git merge-file
  --diff3 -p`, `git add`/`git commit`, markdown serialization, snapshot listing and restore-from-git
  for the editor UI. The backend **never touches git** — there is exactly one owner of the repo to
  avoid two writers.
- **Backend (owns the knowledge graph):** only the *persistence* half of a restore. `HistoryService.
  restore()` currently reads from git *and* writes to Neo4j; only the Neo4j write (repository + unit
  of work) stays. The PATCH body changes from `{commit_id}` (backend looks it up in git) to carrying
  the restored content, which the loop has already read from git.

Consequence for the history API:

- `GET /api/history/{chapter_id}` (list commits) **moves to the loop** — the loop owns the git repo,
  so backend-side listing becomes obsolete.
- `PATCH /api/history/{chapter_id}` (restore) changes shape: the loop reads the commit from git and
  sends the restored content up; the backend persists it.

### git branch approach rejected

An earlier variant used git branches: branch, commit the unstaged changes, rehydrate in the
background, merge the branch, resolve conflicts. This was rejected because **conflict resolution
became the product** — an always-on edit-edit merge under an actively-typed cursor. The synchronous
single-truth loop above eliminates the merge/conflict-resolver entirely: the latest file always wins.

## 4. The sentence-boundary format rule (settled)

To let `git merge-file` (line-based) resolve at **sentence granularity** rather than paragraph
granularity, hydration normalizes the markdown so that:

- **Paragraph** = a block delimited by a blank line (`\n\n`).
- **Sentence** = one line inside a paragraph: a `<span data-par-id="…">` element
  holding that sentence's text and its paragraph's UUID (repeated on every
  sentence of the paragraph). The span *is* the sentence unit; each paragraph
  is written one sentence-span per line. Sentences carry no id of their own —
  they are re-derived at hydration time. The spaCy pipeline still resolves
  sentence boundaries for text that arrives without spans (hand-typed edits or
  legacy snapshots), so "Dr."
  and "e.g." are handled correctly there.

The rules, stated symmetrically:

- **Newlines are never sentence delimiters.** In span-free text, sentence-splitting uses NLP logic
  only (`nlp(...).sents`); in span-wrapped text the spans delimit the sentences.
- **A newline mid-sentence is ordinary whitespace.** Renderers treat it as soft wrapping; the parser
  ignores it for sentence structure. A user may place a newline mid-sentence freely (inside a span
  it is preserved byte-for-byte).
- **A forced mid-sentence break** is written as `\` followed by a newline (CommonMark hard-break
  syntax). The hydrator must preserve this and not strip or reinterpret it.
- **Parse side:** span-wrapped sentences are read from the spans; span-free text is split on the
  terminator regardless of the newline. The per-line layout is a *merge* convenience, not a parsing
  requirement.
- **Write side:** emit one sentence-span per line; span-free input is split and wrapped first.

The one whitespace distinction to keep straight:

| Whitespace | Meaning | For |
|---|---|---|
| Sentence-ender line break | sentence boundary (writer-inserted per span) | `git merge-file` granularity |
| Blank line `\n\n` | paragraph boundary | block structure + `git merge-file` |

## 5. The cross-process, multi-tasking consideration

The markdown editor runs in a separate process from the rehydrator. Because of multi-tasking, file
changes can arrive *while* rehydration is running. The synchronous loop handles this by
discarding-and-restarting on conflict, rather than trying to run concurrent work or merge.

### Idempotent, minimal-diff hydration requirement

The scheme depends on rehydration's **write** being **minimal-diff** — it must touch only the
changed paragraph/sentence and preserve the rest byte-for-byte. If hydration rewrote the whole
chapter, every save would conflict. **This minimal-write property is load-bearing and must be
verified/guaranteed.**

### Starvation and the fail-tolerance setting

If file changes are frequent and overlapping, rehydration may not complete for several iterations.
The mitigation is a configured **fail-tolerance**: a number of allowed consecutive failures, after
which file changes are **halted (the editor frozen)** so rehydration can finish. This is
configurable and is a **later feature**, because freezing requires owning the editor.

### The freeze vs editor-agnostic tension

"Freeze the editor to let rehydration finish" is incompatible with *any off-the-shelf* markdown
editor (you cannot freeze VSCode/nano). In the off-the-shelf phase, starvation is bounded by the
fail-tolerance + debounce/drain, accepting that the knowledge graph may lag the file. The freeze —
and frequent-save push updates — only become possible once we own the editor.

So the design is: **the rehydration engine is editor-agnostic and durable; only the "how the user
types" shell changes later.**

## 6. Sentence metadata in the format

The snapshot writer serializes the hierarchy into markdown and wraps every
sentence in a `<span data-par-id="…">` element carrying its paragraph's UUID
(repeated on every sentence span of the paragraph). The parser reads the spans
back onto the Paragraph model objects, so paragraph *identity* survives
serialization. Sentences carry no id in the format: they are re-derived at
write and parse time (from the spans' text, or with spaCy for span-free text)
and assigned fresh UUIDs.

The README's aspirational metadata — JSON-in-HTML-comment blobs for non-text
attrs (e.g. premise, elevator pitch) and `<span data-attr>` inline metadata —
remains out of scope; only the paragraph identity spans (`data-par-id`) are
implemented today. They reuse the span mechanism described below for the
later NLP-derived spans.

With the single-truth loop there is only ever one writer of record; embedding
paragraph-level identity in the format keeps the graph aligned with the file
across rehydration and makes paragraph identity stable for the merge
and freeze features to come, at negligible cost.

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
  does not emit spans.
- **The FE renders spans; it does not derive them.** Rendering is the only FE responsibility for
  semantics.
- **Granularity is the sentence.** Spans are scoped to a sentence's text; a sentence split re-derives
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

## 7. Sequence of implementation

This is the order we expect to build, matching the dependencies above; it is subject to adjustment
during planning.

1. **Backend API additions:** new `.../rehydrate` endpoints (chapter/paragraph/sentence) and the
   optional `?format=markdown` on GET; the history restore endpoint is reduced to persistence-only
   (accept resolved content, stop reading git). The rehydrate path must also **emit semantic spans**
   (`data-triple`/`data-spo` and other NLP attributes) back into the normalized markdown. Remove
   backend code no longer needed (delete, per the requirement to delete unused code).
2. **Synchronous save-and-rehydrate engine** (editor-agnostic): owns the markdown files + git repo.
   On save: parse the new markdown file, diff it against the chapter read from the knowledge graph
   (changed / new / deleted paragraphs, classified from `data-par-id` identity + parsed sentence
   text), then rehydrate synchronously before the editor continues. Owns snapshot listing and
   restore-from-git. Editor and file-save mechanics are deferred (later). The former async loop
   (file-watch, `git merge-file --diff3 -p`, cancel-and-rerun) is dropped per **Synchronous
   save-and-rehydrate** above.
   - Enforce the sentence-boundary / minimal-write normalization rules.
   - `SnapshotWriter`/`SnapshotReader` and all git logic are moved here from the backend.
3. **Remove the old front end** (React + Tiptap/ProseMirror) and any backend code only it used.
4. **Editor integration** (later): wires the editor's save into the synchronous rehydrate step.
   Paragraph identity is already in the format (`data-par-id` spans).

### Front-end & loop platform (PC-only variant, decided)

For the **PC-only** target (Linux/macOS/Windows) with a WYSIWYG-primary editor plus a CodeMirror
markdown source mode and the NLP span views: **Electron + TypeScript, with the editor and the loop
in the same Node process.** Only Tauri was a serious alternative; it was rejected because its shell
is Rust, which would force the loop into a second language or a Rust sidecar. Keeping both the editor
and the loop in one Node process means one language for the whole PC-local stack.

Concretely:

- **Editor:** CodeMirror 6 for the markdown source mode; browser markdown rendering / WYSIWYG
  (markdown-it + HTML, or TipTap) for the primary view; the NLP semantics render as styled/clickable
  spans already present in the text (`data-triple` / `data-spo`, etc.). The editor and the sync
  engine share the markdown serializer and the git/file logic.
- **Sync engine (same process):** parses the saved markdown file, diffs against the knowledge graph,
  rehydrates synchronously through the API, then `git add` / `git commit`. Also owns snapshot
  listing and restore-from-git.
- **Portability note:** this decision is for PC-only. If mobile/iPad ever becomes a requirement, the
  flat markdown + span format is unchanged and a Flutter client could drive the same loop via the API;
  only the editor shell differs.

The earlier "loop process language" open question is resolved by this decision.

## 8. Alternatives considered (and why not)

- **Terminal SPA (`ink`, Go bubbletea, Rust ratatui).** Clean for a desktop tool, but **cannot
  reach iOS/Android** — incompatible with the real requirement. Rejected on portability, not on merit.
- **Browser + hand-rolled markdown editor.** Viable (reduces to flat-text→sentence logic), but the
  loop above makes *any* editor work, so an own-editor is deferred and optional.
- **Flutter + a structure-aware editor (AppFlowy Editor / Super Editor).** A strong rewrite path for a
  native app; its tree model matches our hierarchy. Not chosen as the primary path because the
  file-based rehydration engine is editor-agnostic; Flutter (or any client) could later drive it.
- **Browser + Tiptap/ProseMirror (status quo).** Kept the least new code but did not solve the async
  restructure race; the framework was not the bottleneck, so continuing to invest there was deemed
  lower value than the file-based redesign.
- **git-branch merge scheme.** Rejected; see §3.

## 9. Open questions before trust

These must be settled before/while building, not deferred silently:

1. **Minimal-write guarantee** — confirm the rehydrator writes only the changed region, or make it
   so. This is the load-bearing assumption.
2. **Cost vs frequency** — is a single rehydrate pass cheap enough that discard-and-rerun is
   acceptable under realistic save rates? (Drives the fail-tolerance default.)
3. **Conflict-policy granularity** — with paragraph-level diff3 conflicts firing on benign overlaps,
   do we (a) accept discard-and-rerun at paragraph granularity, or (b) reserve sentence-level merging
   for the own-editor phase?
4. **`\` hard-break preservation** — ensure the write-side normalizer never mangles a user's explicit
   backslash-newline.
5. **Span re-derivation on sentence re-split** — confirm how the rehydrator emits/re-emits spans
   when a sentence splits/merges, and that this is scoped and idempotent.
