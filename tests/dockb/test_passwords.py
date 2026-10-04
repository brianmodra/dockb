"""Tests for the password policy and its Argon2id hashing.

One hash or verification costs about 30ms at the production parameters, so these tests
keep to as few of them as they can, and pin the properties that cost something — the
parameters, the salt, the cost of rejecting a user — structurally rather than by
timing. A timing assertion would be slower than the operation it measures and would
fail on a loaded machine.
"""

from __future__ import annotations

import hashlib
import inspect
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import argon2
import pytest
from argon2 import extract_parameters
from argon2.low_level import Type

from dockb import passwords
from dockb.passwords import (
    DUMMY_HASH,
    MAXIMUM_LENGTH,
    MINIMUM_LENGTH,
    PasswordPolicyError,
    hash_password,
    pepper_from,
    verify_password,
)

_PEPPER = pepper_from("a server secret for the tests")
_OTHER_PEPPER = pepper_from("a different server secret")

_LONGEST_ALLOWED = "a" * MAXIMUM_LENGTH
_TOO_LONG = "a" * (MAXIMUM_LENGTH + 1)
_SHORTEST_REFUSED = "a" * (MINIMUM_LENGTH - 1)


def _verify_pair(pair: tuple[str, str]) -> bool:
    return verify_password(_PEPPER, *pair)


def _hash_pair(pair: tuple[bytes, str]) -> str:
    return hash_password(pair[0], pair[1])


# ---------------------------------------------------------------- the policy


def test_the_policy_bounds_are_the_ones_the_specification_pins():
    # Everything below states the bounds in terms of these constants, so nothing else here
    # would notice them being changed. NIST SP 800-63B's length guidance, and the maximum
    # that keeps one Argon2id operation affordable.
    assert (MINIMUM_LENGTH, MAXIMUM_LENGTH) == (12, 128)


def test_nothing_here_waits_for_an_event_loop():
    # The CLI generates and resets passwords in a plain synchronous process, so a coroutine
    # here would break it with no other symptom. Only the login route is asynchronous, and
    # it offloads this module with `run_in_threadpool`.
    assert not inspect.iscoroutinefunction(hash_password)
    assert not inspect.iscoroutinefunction(verify_password)


@pytest.mark.parametrize(
    "password",
    [
        pytest.param("a" * MINIMUM_LENGTH, id="exactly the minimum"),
        pytest.param(_LONGEST_ALLOWED, id="exactly the maximum"),
        pytest.param("correct horse battery staple", id="no digits, capitals or symbols"),
        pytest.param("é" * MINIMUM_LENGTH, id="accented, so more bytes than characters"),
        pytest.param("\U0001f511" * MINIMUM_LENGTH, id="astral, four bytes per character"),
    ],
)
def test_the_policy_accepts_a_password_that_obeys_it(password):
    # Exercised through the hasher because that is the only way in: the policy is enforced
    # where the hashing happens, so a caller cannot skip it by hashing directly.
    assert isinstance(hash_password(_PEPPER, password), str)


def test_the_policy_imposes_no_composition_rules():
    # NIST SP 800-63B prefers length over character classes: rules about capitals, digits
    # and symbols push people towards predictable substitutions.
    assert isinstance(hash_password(_PEPPER, "aaaaaaaaaaaaa"), str)


@pytest.mark.parametrize(
    "password",
    [
        pytest.param(_SHORTEST_REFUSED, id="one below the minimum"),
        pytest.param(_TOO_LONG, id="one above the maximum"),
    ],
)
def test_the_policy_refuses_a_password_that_breaks_it(password):
    with pytest.raises(PasswordPolicyError):
        hash_password(_PEPPER, password)


def test_a_refused_password_says_which_bound_it_broke():
    # The CLI prints this to stderr and the route returns it, so it has to name the number.
    # Checked against both bounds at once, because "12" is a substring of "128" and the
    # wrong message would otherwise pass.
    with pytest.raises(PasswordPolicyError) as too_short:
        hash_password(_PEPPER, _SHORTEST_REFUSED)
    assert "12" in str(too_short.value) and "128" not in str(too_short.value)
    with pytest.raises(PasswordPolicyError) as too_long:
        hash_password(_PEPPER, _TOO_LONG)
    assert "128" in str(too_long.value)


def test_a_too_long_password_is_refused_before_it_is_hashed(monkeypatch):
    # The maximum exists to bound the cost of one Argon2id operation, so it has to be
    # checked before the work rather than after it. Refusing afterwards gives the same
    # answer and none of the protection, and only a watcher can tell the two apart.
    hasher = Mock(wraps=passwords._HASHER)
    monkeypatch.setattr(passwords, "_HASHER", hasher)
    with pytest.raises(PasswordPolicyError):
        hash_password(_PEPPER, _TOO_LONG)
    assert hasher.hash.call_args_list == []


def test_the_maximum_counts_characters_and_not_bytes():
    # The same 128 characters as the longest allowed password, four bytes each. A policy
    # counting bytes would refuse this as 512.
    assert isinstance(hash_password(_PEPPER, "\U0001f511" * MAXIMUM_LENGTH), str)


def test_a_generated_password_is_exempt_from_the_minimum():
    # Its entropy comes from how it was made, not from how long it is.
    assert isinstance(hash_password(_PEPPER, "kR7-vQ2", generated=True), str)


def test_a_generated_password_is_still_bound_by_the_maximum():
    # Exempt from the minimum is not exempt from the policy.
    with pytest.raises(PasswordPolicyError):
        hash_password(_PEPPER, _TOO_LONG, generated=True)


def test_an_empty_password_is_refused_even_when_generated():
    # The exemption is from the minimum length, not from being a password. Without this a
    # caller passing generated=True could fill the column with a hash of nothing.
    with pytest.raises(PasswordPolicyError):
        hash_password(_PEPPER, "", generated=True)


# ------------------------------------------------------------------- hashing


def test_a_hash_is_not_the_password():
    password = "correct horse battery staple"
    assert password not in hash_password(_PEPPER, password)


def test_a_hash_verifies_against_its_own_password():
    hashed = hash_password(_PEPPER, _LONGEST_ALLOWED)
    assert verify_password(_PEPPER, _LONGEST_ALLOWED, hashed)


def test_a_hash_refuses_a_different_password():
    hashed = hash_password(_PEPPER, _LONGEST_ALLOWED)
    assert not verify_password(_PEPPER, "b" * MAXIMUM_LENGTH, hashed)


def test_the_same_password_hashes_differently_each_time():
    # A salt per hash, so two accounts that choose the same password do not share a hash
    # and no precomputed table covers both.
    assert hash_password(_PEPPER, _LONGEST_ALLOWED) != hash_password(_PEPPER, _LONGEST_ALLOWED)


def test_a_hash_carries_argon2id_and_the_pinned_owasp_profile():
    # OWASP's strongest listed Argon2id profile: m=47104 KiB (46 MiB), t=1, p=1. Asserted
    # as the numbers the specification pins rather than against the module's constants, so
    # that quietly lowering them fails here.
    parameters = extract_parameters(hash_password(_PEPPER, _LONGEST_ALLOWED))
    assert parameters.type is Type.ID
    assert (parameters.memory_cost, parameters.time_cost, parameters.parallelism) == (47104, 1, 1)


# ------------------------------------------------------- the unknown-username cost


def test_the_dummy_hash_costs_exactly_what_a_real_one_costs():
    # The dummy exists so an unknown username costs what a wrong password costs. Hashing
    # it more cheaply reinstates the difference it exists to remove, so this compares it
    # with a real hash's parameters instead of with a second copy of the numbers.
    assert extract_parameters(DUMMY_HASH) == extract_parameters(hash_password(_PEPPER, _LONGEST_ALLOWED))


def test_the_dummy_hash_verifies_nothing():
    assert not verify_password(_PEPPER, _LONGEST_ALLOWED, DUMMY_HASH)


def test_an_account_with_no_password_still_pays_for_a_verification(monkeypatch):
    # `password_hash` is NULL for a provider-only row. Turning that away without hashing
    # would make "this account has no password" a free answer for anyone who can guess a
    # name, which is the same oracle the dummy exists to close. Asserted by watching the
    # hasher rather than by timing, which would be both slower and less reliable.
    hasher = Mock(wraps=passwords._HASHER)
    monkeypatch.setattr(passwords, "_HASHER", hasher)
    assert verify_password(_PEPPER, "any password at all", None) is False
    assert [call.args[0] for call in hasher.verify.call_args_list] == [DUMMY_HASH]


# --------------------------------------------------------------------- the pepper


def test_a_hash_made_under_one_pepper_does_not_verify_under_another():
    # The point of the pepper: a stolen dockb_app.db cannot be checked against guesses on
    # the attacker's machine, because they cannot produce what Argon2 was given.
    hashed = hash_password(_PEPPER, _LONGEST_ALLOWED)
    assert not verify_password(_OTHER_PEPPER, _LONGEST_ALLOWED, hashed)


def test_the_pepper_comes_from_the_secret_and_only_the_secret():
    assert pepper_from("a server secret") == pepper_from("a server secret")
    assert pepper_from("a server secret") != pepper_from("a different server secret")


def test_the_pepper_is_not_the_key_the_tokens_are_encrypted_with():
    # TokenEncryptor takes sha256(secret) outright. Reusing those bytes here would make one
    # leaked value both the token key and the password pepper, and the two could no longer
    # be rotated apart.
    digest = hashlib.sha256(b"a server secret").digest()
    assert pepper_from("a server secret") != digest


@pytest.mark.parametrize("secret", ["", "   "], ids=["empty", "blank"])
def test_an_empty_secret_is_refused_rather_than_giving_an_unkeyed_pepper(secret):
    # HMAC takes an empty key and becomes a plain hash, so a DOCKB_SECRET_KEY that is set but
    # blank would drop the protection while still producing hashes that look entirely normal.
    with pytest.raises(ValueError):
        pepper_from(secret)


def test_the_password_itself_never_reaches_argon2():
    # Argon2 is handed an HMAC of the password, so the string cannot be recovered from the
    # hash by anyone who lacks the pepper.
    assert _LONGEST_ALLOWED.encode("utf-8") not in passwords._keyed(_PEPPER, _LONGEST_ALLOWED)


# --------------------------------------------------------------- verification


def test_a_corrupt_stored_hash_is_refused_rather_than_raised():
    # A value that did not come out of argon2 must not become a 500 on the login route.
    assert verify_password(_PEPPER, "any password at all", "not-an-argon2-hash") is False


def test_the_one_shared_hasher_survives_concurrent_use():
    # The login route calls into this module from a threadpool precisely so that concurrent
    # sign-ins do not queue behind one another, so the single module-level hasher is entered
    # from several threads at once. Argon2id holds no mutable state between calls, and this
    # is what would notice if that ever changed. Four at the production 46 MiB, which is as
    # many as this can afford at once.
    submitted = [f"concurrent sign-in number {index}" for index in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        hashed = list(pool.map(_hash_pair, [(_PEPPER, password) for password in submitted]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(_verify_pair, list(zip(submitted, hashed, strict=True))))
    assert all(verified)
    assert len(set(hashed)) == len(hashed), "one salt for all of them would collapse these"


def test_verification_does_not_apply_the_policy():
    # Keyed and hashed exactly as this module does it, but around the policy, standing in
    # for a password stored under an older or looser rule. Whether it satisfies today's
    # policy is not what decides whether it matches. Cheaply hashed, because a real hash
    # here would buy nothing: the parameters are not what is under test.
    cheap = argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    legacy = cheap.hash(passwords._keyed(_PEPPER, "short"))
    assert verify_password(_PEPPER, "short", legacy)


def test_verification_never_raises_the_policy_error():
    # The other half of the same rule: a password too short to be stored today still reaches
    # argon2 rather than being turned away, so that this path costs the same as any other
    # rejection and cannot be used to recognise a short password.
    assert verify_password(_PEPPER, "short", None) is False
    assert verify_password(_PEPPER, "short", DUMMY_HASH) is False


def test_passwords_are_compared_as_submitted_and_not_normalised():
    # NIST SP 800-63B: compare as submitted. Normalising would let a password the person
    # did not choose verify against one they did, silently. Written as escapes because the
    # two forms are indistinguishable on screen and an editor will quietly fold them
    # together: the composed e-acute, then the same letter as "e" plus a combining acute.
    tail = " and then some"  # long enough for the policy to accept either form
    composed = "caf\u00e9" + tail
    decomposed = "cafe\u0301" + tail
    assert composed != decomposed, "these must be different byte sequences"
    assert unicodedata.normalize("NFC", decomposed) == composed, "and the same text"
    assert not verify_password(_PEPPER, composed, hash_password(_PEPPER, decomposed))
