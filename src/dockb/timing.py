"""Per-request timing statistics.

The HTTP layer installs a :class:`Timings` instance via :func:`trace`, and
``measure()`` calls anywhere in the request accumulate named stage durations.
Without an active trace ``measure()`` is a no-op, so services keep working in
unit tests and outside the web request cycle. ``_perf_counter`` is a module
alias so tests can drive a fake clock.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_timings_var: ContextVar[Timings | None] = ContextVar("dockb_timings", default=None)

_perf_counter = time.perf_counter


class Timings:
    """Accumulates named stage timings for a single request."""

    def __init__(self) -> None:
        self._first_seen: list[str] = []
        self._totals: dict[str, float] = {}
        self._stack: list[tuple[str, float]] = []

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Time *name* for the duration of the block, adding to its total."""
        if name not in self._totals:
            self._first_seen.append(name)
            self._totals[name] = 0.0
        start = _perf_counter()
        self._stack.append((name, start))
        try:
            yield
        finally:
            _, start = self._stack.pop()
            elapsed_ms = (_perf_counter() - start) * 1000
            self._totals[name] += elapsed_ms

    def summary(self) -> str:
        """One line per stage in first-use order, e.g. ``"load 3ms, save 7ms"``."""
        return ", ".join(f"{name} {self._totals[name]:.0f}ms" for name in self._first_seen)


@contextmanager
def trace() -> Iterator[Timings]:
    """Install a fresh :class:`Timings` for the duration of the block.

    Restores the previous value on exit so traces never leak across requests.
    """
    timings = Timings()
    token = _timings_var.set(timings)
    try:
        yield timings
    finally:
        _timings_var.reset(token)


def measure(name: str) -> AbstractContextManager[None]:
    """Time *name* against the active trace, or do nothing without one."""
    timings = _timings_var.get()
    if timings is None:
        return nullcontext()
    return timings.measure(name)


class TimingMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """Log one INFO line per HTTP request: total time plus stage breakdown.

    Installs a fresh :class:`Timings` for the request so ``measure()`` calls in
    services accumulate a per-stage breakdown, and wraps ``call_next`` in a
    timer for the total. Falls back to status 500 when the request raises.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        with trace() as timings:
            start = _perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                self._log(request, 500, start, timings)
                raise
            self._log(request, response.status_code, start, timings)
            return response

    @staticmethod
    def _log(request: Request, status: int, start: float, timings: Timings) -> None:
        total_ms = (_perf_counter() - start) * 1000
        breakdown = timings.summary()
        suffix = f" | {breakdown}" if breakdown else ""
        logger.info(
            "request %s %s %s %.0fms%s",
            request.method,
            request.url.path,
            status,
            total_ms,
            suffix,
        )
