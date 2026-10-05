"""Tests for LoginThrottle — backoff that lengthens and then decays."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dockb.infrastructure.session.login_throttle import LoginThrottle

_START = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


class _Clock:
    """A hand-advanced clock, so the backoff is tested without sleeping."""

    def __init__(self) -> None:
        self.now = _START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _throttle(**kwargs) -> tuple[LoginThrottle, _Clock]:
    clock = _Clock()
    return LoginThrottle(clock, **kwargs), clock


class TestDelayGrows:
    def test_first_failures_are_free(self) -> None:
        """A few misses should not lock anyone out of their own account."""
        throttle, _ = _throttle(max_attempts=3)
        for _ in range(2):
            throttle.record_failure("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0

    def test_delay_starts_at_the_attempt_threshold(self) -> None:
        throttle, _ = _throttle(max_attempts=3, base_delay=2.0)
        for _ in range(3):
            throttle.record_failure("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") == 2.0

    def test_delay_doubles_with_each_further_failure(self) -> None:
        throttle, _ = _throttle(max_attempts=2, base_delay=2.0)
        delays = []
        for _ in range(3):
            throttle.record_failure("abby", "10.0.0.1")
            delays.append(throttle.delay_for("abby", "10.0.0.1"))
        # The first failure is still free; the threshold is where the charge starts.
        assert delays == [0.0, 2.0, 4.0]

    def test_the_wait_is_served_after_the_reported_delay(self) -> None:
        """retry_after has to be true, or the caller waits and is refused anyway."""
        throttle, clock = _throttle(max_attempts=2, base_delay=4.0)
        throttle.record_failure("abby", "10.0.0.1")
        throttle.record_failure("abby", "10.0.0.1")
        owed = throttle.delay_for("abby", "10.0.0.1")
        assert owed == 4.0
        clock.advance(owed)
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0

    def test_part_serving_the_wait_still_owes_the_rest(self) -> None:
        throttle, clock = _throttle(max_attempts=2, base_delay=4.0)
        throttle.record_failure("abby", "10.0.0.1")
        throttle.record_failure("abby", "10.0.0.1")
        clock.advance(3)
        assert throttle.delay_for("abby", "10.0.0.1") == 1.0

    def test_delay_is_capped(self) -> None:
        """A patient attacker must not be able to buy an unbounded stall."""
        throttle, _ = _throttle(max_attempts=1, base_delay=1.0, max_delay=30.0)
        for _ in range(20):
            throttle.record_failure("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") == 30.0


class TestTwoDimensions:
    def test_username_failures_throttle_that_username(self) -> None:
        throttle, _ = _throttle(max_attempts=2)
        for _ in range(2):
            throttle.record_failure("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") > 0.0
        # A different username from a different address has nothing against it. The IP
        # is checked too, because a failure against one account throttles the address
        # it came from, and that must not read as this account being suspect.
        assert throttle.delay_for("robin", "10.0.0.9") == 0.0

    def test_ip_failures_throttle_the_address_not_the_user(self) -> None:
        """One address spraying many usernames must be slowed, not one account."""
        throttle, _ = _throttle(max_attempts=2)
        for index in range(2):
            throttle.record_failure(f"user{index}", "10.0.0.1")
        assert throttle.delay_for("someone-else", "10.0.0.1") > 0.0
        assert throttle.delay_for("user0", "10.0.0.9") == 0.0

    def test_a_username_cannot_collide_with_an_ip(self) -> None:
        """A username spelled like an address must not touch that address's counter."""
        throttle, _ = _throttle(max_attempts=2)
        for _ in range(3):
            throttle.record_failure("abby", "10.0.0.1")
        # The address is throttled...
        assert throttle.delay_for("robin", "10.0.0.1") > 0.0
        # ...but an account named after that address, arriving from elsewhere, is not.
        assert throttle.attempts("10.0.0.1", "192.168.0.1") == 0
        assert throttle.delay_for("10.0.0.1", "192.168.0.1") == 0.0

    def test_either_dimension_alone_is_enough_to_throttle(self) -> None:
        throttle, _ = _throttle(max_attempts=2)
        throttle.record_failure("abby", "10.0.0.1")
        throttle.record_failure("robin", "10.0.0.1")
        assert throttle.delay_for("robin", "10.0.0.1") > 0.0


class TestDecay:
    def test_failures_decay_after_a_quiet_period(self) -> None:
        """An attempt tomorrow must not still be paying for one tonight."""
        throttle, clock = _throttle(max_attempts=1, decay=60.0)
        throttle.record_failure("abby", "10.0.0.1")
        clock.advance(61)
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0

    def test_failures_persist_inside_the_quiet_period(self) -> None:
        """Serving the wait is not the same as forgetting: the next miss costs more."""
        throttle, clock = _throttle(max_attempts=1, base_delay=1.0, decay=60.0)
        throttle.record_failure("abby", "10.0.0.1")
        clock.advance(30)
        assert throttle.attempts("abby", "10.0.0.1") == 1
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0
        throttle.record_failure("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") == 2.0

    def test_a_failure_after_decay_restarts_the_count(self) -> None:
        throttle, clock = _throttle(max_attempts=3, base_delay=4.0, decay=60.0)
        for _ in range(3):
            throttle.record_failure("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") == 4.0
        clock.advance(61)
        throttle.record_failure("abby", "10.0.0.1")
        assert throttle.attempts("abby", "10.0.0.1") == 1
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0

    def test_reading_the_delay_does_not_reset_the_counter(self) -> None:
        """delay_for is asked on every attempt, so it must not be a hidden reset."""
        throttle, clock = _throttle(max_attempts=1, decay=60.0)
        throttle.record_failure("abby", "10.0.0.1")
        clock.advance(61)
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0
        clock.advance(-61)
        assert throttle.attempts("abby", "10.0.0.1") == 1


class TestSuccessClears:
    def test_success_clears_the_username(self) -> None:
        """Someone who fumbled twice and then got it right is not left waiting."""
        throttle, _ = _throttle(max_attempts=2)
        for _ in range(2):
            throttle.record_failure("abby", "10.0.0.1")
        throttle.record_success("abby", "10.0.0.1")
        assert throttle.delay_for("abby", "10.0.0.1") == 0.0

    def test_success_clears_the_address_too(self) -> None:
        throttle, _ = _throttle(max_attempts=2)
        for index in range(2):
            throttle.record_failure(f"user{index}", "10.0.0.1")
        throttle.record_success("user0", "10.0.0.1")
        assert throttle.delay_for("user1", "10.0.0.1") == 0.0

    def test_success_leaves_other_keys_alone(self) -> None:
        throttle, _ = _throttle(max_attempts=2)
        for _ in range(2):
            throttle.record_failure("robin", "10.0.0.2")
        throttle.record_success("abby", "10.0.0.1")
        assert throttle.delay_for("robin", "10.0.0.2") > 0.0


class TestIntrospection:
    def test_attempts_reports_the_consecutive_failures(self) -> None:
        throttle, _ = _throttle(max_attempts=10)
        assert throttle.attempts("abby", "10.0.0.1") == 0
        for expected in (1, 2, 3):
            throttle.record_failure("abby", "10.0.0.1")
            assert throttle.attempts("abby", "10.0.0.1") == expected

    def test_attempts_reports_the_worse_of_the_two_keys(self) -> None:
        throttle, _ = _throttle(max_attempts=10)
        throttle.record_failure("abby", "10.0.0.1")
        throttle.record_failure("robin", "10.0.0.1")
        assert throttle.attempts("robin", "10.0.0.1") == 2
