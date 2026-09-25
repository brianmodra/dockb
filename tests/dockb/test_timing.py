"""Tests for the per-request timing statistics module."""

from __future__ import annotations

import threading

import pytest

from dockb import timing


def _install_fake_clock(monkeypatch: pytest.MonkeyPatch, values: list[float]) -> None:
    """Make timing's clock return *values* in call order."""
    calls: list[float] = []

    def fake() -> float:
        value = values[len(calls)]
        calls.append(value)
        return value

    monkeypatch.setattr(timing, "_perf_counter", fake)


class TestTimingsMeasure:
    """Timings.measure records elapsed millisecond durations."""

    def test_records_elapsed(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.010])
        timings = timing.Timings()
        with timings.measure("stage.load"):
            pass
        assert timings.summary() == "stage.load 10ms"

    def test_accumulates_repeated_same_name(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.003, 0.003, 0.008])
        timings = timing.Timings()
        with timings.measure("neo4j.read"):
            pass
        with timings.measure("neo4j.read"):
            pass
        assert timings.summary() == "neo4j.read 8ms"

    def test_nested_measures_both_recorded(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.002, 0.006, 0.010])
        timings = timing.Timings()
        with timings.measure("outer"):
            with timings.measure("inner"):
                pass
        assert timings.summary() == "outer 10ms, inner 4ms"

    def test_records_when_body_raises(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.010])
        timings = timing.Timings()
        with pytest.raises(RuntimeError):
            with timings.measure("stage.fail"):
                raise RuntimeError("boom")
        assert timings.summary() == "stage.fail 10ms"

    def test_summary_rounds_to_integer_ms(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.000004])
        timings = timing.Timings()
        with timings.measure("fast"):
            pass
        assert timings.summary() == "fast 0ms"

    def test_summary_preserves_first_use_order(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.001, 0.001, 0.002, 0.002, 0.100])
        timings = timing.Timings()
        with timings.measure("repo.chapter.load"):
            pass
        with timings.measure("stage.apply_chapter_file"):
            pass
        with timings.measure("repo.chapter.load"):
            pass
        assert timings.summary().startswith("repo.chapter.load")
        assert timings.summary().endswith("stage.apply_chapter_file 1ms")


class TestTrace:
    """trace() installs an active Timings for the duration of its block."""

    def test_module_measure_accumulates_inside_trace(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.005])
        with timing.trace() as timings:
            with timing.measure("stage.read"):
                pass
        assert timings.summary() == "stage.read 5ms"

    def test_measure_is_noop_without_trace(self) -> None:
        with timing.measure("stage.orphan"):
            pass

    def test_trace_yields_fresh_timings_each_call(self) -> None:
        with timing.trace() as first:
            pass
        with timing.trace() as second:
            pass
        assert first is not second
        assert first.summary() == ""
        assert second.summary() == ""

    def test_trace_restores_previous_value_on_exit(self, monkeypatch) -> None:
        _install_fake_clock(monkeypatch, [0.0, 0.001, 0.001, 0.002])
        with timing.trace():
            with timing.trace():
                pass
            # nested trace exited; outer trace is still active
            with timing.measure("after.inner"):
                pass
        # after outer trace exited, module measure is a no-op again
        with timing.measure("outside"):
            pass

    def test_trace_isolated_between_threads(self) -> None:
        """A trace in another thread never contaminates the caller's timings."""
        outer = timing.Timings()
        token = timing._timings_var.set(outer)  # pylint: disable=protected-access
        try:
            other: list[timing.Timings] = []

            def worker() -> None:
                with timing.trace() as t:
                    other.append(t)
                    with timing.measure("thread.stage"):
                        pass

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

            with timing.measure("main.stage"):
                pass
            assert "main.stage" in outer.summary()
            assert "thread.stage" not in outer.summary()
            assert "thread.stage" in other[0].summary()
            assert "main.stage" not in other[0].summary()
        finally:
            timing._timings_var.reset(token)  # pylint: disable=protected-access
