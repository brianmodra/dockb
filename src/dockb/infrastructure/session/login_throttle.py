"""Exponential backoff on password sign-in attempts, per username and per IP address."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

Clock = Callable[[], datetime]

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_BASE_DELAY = 1.0
_DEFAULT_MAX_DELAY = 300.0
_DEFAULT_DECAY = 900.0


@dataclass
class _Failures:
    """Consecutive failures recorded against one key, and when the last arrived."""

    count: int
    last_failure: datetime


class LoginThrottle:
    """Lengthen the wait after consecutive failed sign-ins, per username and per IP.

    Backoff, not lockout. DockB's user set is small and known, so a lockout is a weapon
    that anyone can point at the one legitimate user — for a single-user install that user
    is the owner. Backoff slows the same attacker while never closing the door to the
    person who owns it.

    A delay is charged once a key passes ``max_attempts`` failures, and doubles with each
    failure after that up to ``max_delay``. Failures decay back to zero after ``decay``
    seconds of quiet, so an unrelated attempt tomorrow is not still paying for today.

    Counters live in memory and reset on restart, matching ``SessionManager``: the limit
    is therefore per server process, not per deployment. That is accepted, since the
    process is the thing an attacker is throttled against and restarting it is not
    something they can do.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        clock: Clock,
        *,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        base_delay: float = _DEFAULT_BASE_DELAY,
        max_delay: float = _DEFAULT_MAX_DELAY,
        decay: float = _DEFAULT_DECAY,
    ) -> None:
        self._clock = clock
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._decay = decay
        self._failures: dict[str, _Failures] = {}
        self._lock = threading.Lock()

    def delay_for(self, username: str, client_ip: str) -> float:
        """Return the seconds *username* or *client_ip* must still wait before another attempt.

        The wait is measured from when the key's last failure arrived, so serving it lets
        the next attempt through rather than being refused for the same count. That keeps
        the delay honest: ``RateLimitedError`` reports how long is genuinely left, and
        waiting that long works. Only a failure that gets through raises the count, so
        simply hammering the endpoint during a wait does not push it further out.

        Reading is free of side effects, so a stale run of failures is treated as zero
        here and cleared by the next ``record_failure``.
        """
        with self._lock:
            owed = [self._owed(key) for key in self._keys(username, client_ip)]
        return max(owed)

    def record_failure(self, username: str, client_ip: str) -> None:
        """Count one failed attempt against both *username* and *client_ip*."""
        now = self._clock()
        with self._lock:
            for key in self._keys(username, client_ip):
                # Read through _current so a stale run restarts at one rather than
                # carrying yesterday's total into today's first attempt.
                self._failures[key] = _Failures(count=self._current(key) + 1, last_failure=now)

    def record_success(self, username: str, client_ip: str) -> None:
        """Clear both counters, so a user who fumbles and then signs in is not left waiting."""
        with self._lock:
            for key in self._keys(username, client_ip):
                self._failures.pop(key, None)

    def attempts(self, username: str, client_ip: str) -> int:
        """Return the consecutive failures recorded against *username* or *client_ip*."""
        with self._lock:
            return max(self._current(key) for key in self._keys(username, client_ip))

    @staticmethod
    def _keys(username: str, client_ip: str) -> tuple[str, str]:
        """Return the two counters this attempt touches, kept apart by a prefix.

        The prefix matters: a username that happens to look like an address would
        otherwise read and write the address's counter.
        """
        return f"username:{username}", f"ip:{client_ip}"

    def _current(self, key: str) -> int:
        """Return *key*'s consecutive failure count, or zero if the run has gone stale."""
        failures = self._failures.get(key)
        if failures is None or self._elapsed(failures) >= self._decay:
            return 0
        return failures.count

    def _owed(self, key: str) -> float:
        """Return the seconds still to be served on *key*."""
        failures = self._failures.get(key)
        if failures is None:
            return 0.0
        return max(0.0, self._delay_for_count(self._current(key)) - self._elapsed(failures))

    def _elapsed(self, failures: _Failures) -> float:
        """Return the seconds since *failures*' last failure arrived."""
        return (self._clock() - failures.last_failure).total_seconds()

    def _delay_for_count(self, count: int) -> float:
        """Return the delay owed after *count* consecutive failures."""
        if count < self._max_attempts:
            return 0.0
        # 2.0 rather than 2: an int exponent leaves int ** int typed as Any, which loses
        # the float through the multiplication.
        exponent = count - self._max_attempts
        return min(self._base_delay * 2.0**exponent, self._max_delay)
