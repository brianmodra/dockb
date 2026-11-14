# DeleteJob and ReconstructJob

## Executive Summary

This note explains the background jobs that turn edited text into structured, searchable words — for someone changing sentence splitting, tokenization, or how those jobs run. A Job is a unit of work that a single background worker runs one at a time from a queue; ReconstructJob and DeleteJob are the two concrete jobs, and the SentenceTokenizer turns sentence text into Token objects carrying part of speech, lemma, and whitespace.

The tokenizer can also hand back tokens from an already-parsed paragraph, so an import never re-runs spaCy once per sentence. Both paths fold transient formatting runs onto whole tokens, and hydration slices paragraph runs onto each sentence before tokenizing so formatting survives a sentence split. Jobs can be cancelled cooperatively, time out, and report a status, and the queue lets a newer job for the same model replace the older one so rapid edits never pile up duplicate work.

DeleteJob clears existing sentence tokens before reconstruction.
ReconstructJob hydrates a document, chapter, or paragraph, or tokenizes a sentence.

Both are enqueued to the JobQueue and executed by the single background worker.
Jobs are populated via their `set()` method before being enqueued.

# Job

Base class for ReconstructJob and DeleteJob.

A Job is an object that can be enqueued into the JobQueue. The JobQueue runs a
single background worker thread that steps through queued jobs, executes each
one's `run()` method, and then removes it from the queue.

A job also has a `cancel()` method, which marks the job as CANCELLED. If the job
was already running, `cancel()` sets the status flag and calls `on_cancel()`,
allowing the job to stop itself cooperatively (Python threads cannot be forcibly
killed).

A Job maintains its own status as: QUEUED, RUNNING, DONE, CANCELLED, or FAILED.
A job is only executed by the worker if its status is QUEUED at the time of
pickup.

A Job has:
- `run()`: abstract method subclasses implement to do the actual work.
- `timeout`: float in seconds (default 5.0). When the job starts running, the
  worker starts a `threading.Timer` for this duration. If the timer fires before
  `run()` completes, it calls `cancel()`. The timer is cancelled if `run()`
  finishes in time.
- `id`: a unique UUID generated at construction time.
- `result`: stores the result after execution (optional).
- `error`: stores the exception if execution failed.
- `done`: a `threading.Event` that is set after the job finishes (success,
  failure, or cancellation).

If `run()` raises `KeyboardInterrupt` or `SystemExit`, the worker re-raises it,
causing the worker thread to crash. Any other exception is caught, stored in
`error`, the status is set to FAILED, and the queue continues processing.

The `on_cancel()` hook can be overridden by subclasses to perform cleanup when
a running job is cancelled. It is only called if the job was in RUNNING state
at the time of cancellation.

# JobQueue

The JobQueue manages job execution with a single background worker thread.

It has:
- `enqueue(job)`: adds a job to the queue and starts processing if the worker
  is active.
- `cancel_job(job)`: cancels a queued job by its UUID. Calls the job's
  `cancel()` method. Jobs that are already CANCELLED are skipped when picked up.
- `start()`: starts the background worker thread. Safe to call multiple times —
  subsequent calls are no-ops.
- `shutdown(timeout)`: stops the worker and waits for it to finish. Safe to call
  multiple times (idempotent).
- `join(timeout)`: waits until all currently queued jobs are completed. Returns
  a point-in-time snapshot; jobs enqueued after this call returns are not
  waited on.
- `is_running()`: returns True if the worker thread is active and not shutting
  down.
- `list_jobs()`: returns IDs of all jobs still in QUEUED state.
- `reconstruct_jobs` (read-only property): returns a snapshot of the dict mapping
  model UUIDs to their pending ReconstructJob objects.

Each job is assigned a unique UUID on construction, which is used as the key in
the internal queue (`put_nowait(job_id)`).

A ReconstructJob also records the UUID of the model it is for. This is used to
maintain the `reconstruct_jobs` dict. Before adding a new ReconstructJob, if
there is an existing entry for the same model UUID, the old job is cancelled and
replaced. This prevents redundant work when the same model is updated rapidly.

DeleteJob entries are never stored in the `reconstruct_jobs` dict.

# SentenceTokenizer

Tokenizes raw sentence text into `Token` objects using spaCy via a `DocCache`.
Both `ReconstructJob` and `SyncReconstructor` delegate to this class,
keeping the `models` layer free of spaCy awareness. The `tokenize()` method
takes `(text: str, doc_cache: DocCache, format_runs=())` and returns a
`list[Token]` with POS, lemma, whitespace, and other spaCy-derived attributes
populated. The `tokens_from_doc()` method builds the same tokens from an
already-parsed `Doc` or sentence `Span`, with the same optional runs, which
lets the markdown import tokenize every sentence of a paragraph from that
paragraph's single parse instead of re-running spaCy per sentence.

`apply_format_runs()` maps each run onto the tokens whose character extent it
touches. A token's extent includes its trailing whitespace, and a run that
touches any part of a token formats the whole token. Runs do not overlap, so at
most one applies. Callers clear the source `format_runs` after a successful
tokenization so a retry can still apply them.

# Sentence split detection

The ParagraphHydrator splits paragraph text at spaCy sentence boundaries during
import. It slices the paragraph's formatting runs onto each new sentence with
`slice_runs()`, rebasing each sentence's runs to start at zero, so formatting is
preserved across the split.

ReconstructJob does not currently split an edited sentence into several; it
tokenizes the sentence text it is given. A future split should use `slice_runs()`
for the same run-preserving behavior. The SessionContext can still deliver a
`sentence_split` notification (see controllers/README_API.md **Async
Notifications**).

# Cancelling a ReconstructJob

If a reconstruct is in progress, it can be cancelled. The ReconstructJob class
has an on_cancel method, which calls the SentenceTokenizer cancel method.
This method may be able to cancel the tokenization loop, if it was called during
the process, because it sets an event which is checked in the loop.

# Hydrators

## DocumentHydrator, ChapterHydrator, ParagraphHydrator

These are already introduced in @src/dockb/services/README.md

These hydrators will use the model's text, and split it up into the constituent parts.
ParagraphHydrator also distributes the paragraph's transient `format_runs` onto
the sentences it creates, then clears them from the paragraph.

# Reconstructors

The `Reconstructor` abstract base class is implemented by `SyncReconstructor`
and `AsyncReconstructor`. Both handle all model types (`Document`, `Chapter`,
`Paragraph`, `Sentence`), routing to the appropriate hydrator or tokenizer
based on the model's type.

