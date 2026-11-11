"""The mentions scheduler: one running evaluation per chapter, latest state next."""

from unittest.mock import MagicMock

from dockb.services import mentions_scheduler as scheduler_module
from dockb.services.mentions_scheduler import MentionsScheduler


def _make_job(recorder: list, name: str):
    """A job factory whose job, when run, appends *name* to *recorder* and returns it."""

    def make():
        job = MagicMock()
        job.run.side_effect = lambda: recorder.append(name)
        return job

    return make


def _sync_threads(monkeypatch):
    """Schedule runs its workers synchronously: every order becomes observable."""
    monkeypatch.setattr(scheduler_module, "start_thread", lambda worker: worker())


def test_an_idle_chapter_evaluates_immediately(monkeypatch):
    started = []
    _sync_threads(monkeypatch)
    scheduler = MentionsScheduler()

    scheduler.schedule("c1", _make_job(started, "run"))

    assert started == ["run"]


def test_a_trigger_during_a_run_cancels_it_and_runs_the_fresh_state_next(monkeypatch):
    """The running job sees its cancel event once the newer trigger arrives."""
    runs = []
    _sync_threads(monkeypatch)
    scheduler = MentionsScheduler()

    def make_running():
        job = MagicMock()

        def run():
            assert job.cancel is not None
            runs.append(("first", job.cancel.is_set()))
            scheduler.schedule("c1", make_fresh)  # the newer save's trigger

        job.run.side_effect = run
        return job

    def make_fresh():
        job = MagicMock()
        job.run.side_effect = lambda: runs.append(("fresh", job.cancel is not None and job.cancel.is_set()))
        return job

    scheduler.schedule("c1", make_running)

    assert runs == [("first", False), ("fresh", False)]


def test_a_burst_of_triggers_costs_one_successor_not_one_per_save(monkeypatch):
    """Two saves during one run queue the fresh state once, not twice."""
    runs = []
    _sync_threads(monkeypatch)
    scheduler = MentionsScheduler()
    fresh_jobs_built = []

    def make_running():
        job = MagicMock()

        def run():
            runs.append("first")
            scheduler.schedule("c1", make_fresh)
            scheduler.schedule("c1", make_fresh)

        job.run.side_effect = run
        return job

    def make_fresh():
        fresh_jobs_built.append(1)
        job = MagicMock()
        job.run.side_effect = lambda: runs.append("fresh")
        return job

    scheduler.schedule("c1", make_running)

    assert runs == ["first", "fresh"]
    assert len(fresh_jobs_built) == 1


def test_a_trigger_during_the_successor_runs_the_latest_state_after_it(monkeypatch):
    """A save that lands while the queued fresh run is going still gets evaluated."""
    runs = []
    _sync_threads(monkeypatch)
    scheduler = MentionsScheduler()

    def make_running():
        job = MagicMock()

        def run():
            runs.append("first")
            scheduler.schedule("c1", make_fresh)

        job.run.side_effect = run
        return job

    def make_fresh():
        job = MagicMock()

        def run():
            runs.append("fresh")
            scheduler.schedule("c1", make_latest)

        job.run.side_effect = run
        return job

    def make_latest():
        job = MagicMock()
        job.run.side_effect = lambda: runs.append("latest")
        return job

    scheduler.schedule("c1", make_running)

    assert runs == ["first", "fresh", "latest"]


def test_a_failed_evaluation_leaves_the_slot_free(monkeypatch):
    """An evaluation that raises is logged and swallowed; the chapter stays usable."""
    started = []
    _sync_threads(monkeypatch)
    scheduler = MentionsScheduler()

    def make_failing():
        job = MagicMock()
        job.run.side_effect = ValueError("boom")
        return job

    scheduler.schedule("c1", make_failing)  # raises inside the worker, not to the caller

    scheduler.schedule("c1", _make_job(started, "retried"))
    assert started == ["retried"]


def test_no_two_evaluations_of_one_chapter_run_at_once():
    """Real threads: the queued evaluation starts only after the running one finished."""
    import threading

    scheduler = MentionsScheduler()
    guard = threading.Lock()
    in_run: set[str] = set()
    overlaps: list[str] = []
    running_gate = threading.Event()
    release = threading.Event()
    fresh_started = threading.Event()

    def make_job(name: str):
        def make():
            job = MagicMock()

            def run():
                with guard:
                    if in_run:
                        overlaps.append(name)
                    in_run.add(name)
                if name == "first":
                    running_gate.set()
                    release.wait(2)
                else:
                    fresh_started.set()
                with guard:
                    in_run.discard(name)

            job.run.side_effect = run
            return job

        return make

    scheduler.schedule("c1", make_job("first"))
    assert running_gate.wait(2)
    scheduler.schedule("c1", make_job("fresh"))  # the second save's trigger, mid-run
    assert not fresh_started.wait(0.3)  # no second thread enters while the first runs
    release.set()
    assert fresh_started.wait(2)
    assert not overlaps


def test_distinct_chapters_run_in_turn(monkeypatch):
    started = []
    _sync_threads(monkeypatch)
    scheduler = MentionsScheduler()

    scheduler.schedule("c1", _make_job(started, "c1-run"))
    scheduler.schedule("c2", _make_job(started, "c2-run"))

    assert started == ["c1-run", "c2-run"]
    assert not scheduler._pending  # every evaluation runs and clears its slot
    assert not scheduler._running


def test_distinct_chapters_are_serialized_on_one_worker():
    """Real threads: one worker runs c2 only after c1 finishes, never alongside it."""
    import threading
    import time

    scheduler = MentionsScheduler()
    runs = []
    c1_started = threading.Event()
    release = threading.Event()

    def make_c1():
        def make():
            job = MagicMock()

            def run():
                runs.append("c1-start")
                c1_started.set()
                release.wait(2)
                runs.append("c1-end")

            job.run.side_effect = run
            return job

        return make

    scheduler.schedule("c1", make_c1())
    assert c1_started.wait(2)
    scheduler.schedule("c2", _make_job(runs, "c2"))

    time.sleep(0.2)
    assert runs == ["c1-start"]  # c2 waits behind the busy worker, not beside it
    release.set()
    deadline = time.time() + 2
    while "c2" not in runs and time.time() < deadline:
        time.sleep(0.01)
    assert runs == ["c1-start", "c1-end", "c2"]
