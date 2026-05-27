# DeleteJob and ReconstructJob

DeleteJob clears existing sentence tokens before reconstruction.
ReconstructJob performs tokenization and semantic reconstruction.

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
takes `(text: str, doc_cache: DocCache)` and returns a `list[Token]` with POS,
lemma, whitespace, and other spaCy-derived attributes populated.

# Cancelling a ReconstructJob

If a reconstruct is in progress, it can be cancelled. The ReconstructJob class
has an on_cancel method, which calls the SentenceTokenizer cancel method.
This method may be able to cancel the tokenization loop, if it was called during
the process, because it sets and event which is checked in the loop.

# Hydrators

## DocumentHydator, ChapterHydrator, ParagraphHydrator

These are already introduced in @src/dockb/services/README.md

These hydrators will use the model's text, and split it up into the constutuent parts.

# Reconstructors

The `Reconstructor` abstract base class is implemented by `SyncReconstructor`
and `AsyncReconstructor`. Both handle all model types (`Document`, `Chapter`,
`Paragraph`, `Sentence`), routing to the appropriate hydrator or tokenizer
based on the model's type.

