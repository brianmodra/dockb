"""What a password may be, and the Argon2id hashing of one.

The policy and the hashing parameters are a property of the password rather than of
the layer that happens to handle it, so they live here rather than in the service,
the route or the store: the CLI generates and resets passwords, ``AuthService``
verifies them, the store holds the result, and all of them have to agree on what a
password may be and what a hash of one looks like.

Everything here is synchronous. Argon2id is deliberately slow and memory-hard, so a
caller on the event loop must not call it directly — it would stall every concurrent
request for the whole duration. The login route offloads with
``fastapi.concurrency.run_in_threadpool``; the CLI has no event loop to stall.

Passwords are keyed with a pepper derived from the server secret, which is not stored
alongside them. That stops a stolen ``dockb_app.db`` from being cracked on the attacker's
own machine, and it makes ``DOCKB_SECRET_KEY`` load-bearing: see ``README_auth.md`` §7 for
what that costs when the secret is absent or rotated.

See ``README_auth.md`` §7.
"""

from __future__ import annotations

import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MINIMUM_LENGTH = 12
MAXIMUM_LENGTH = 128

# OWASP's Password Storage Cheat Sheet lists five Argon2id profiles of *equal* defence,
# differing only in how they trade CPU against RAM, so "the OWASP parameters" does not
# name a number on its own. This is the strongest and most RAM-hungry of the five: the
# trade runs the right way for a server, where a sign-in is rare and RAM is not the
# scarce resource. `m=19456, t=2, p=1` is an equal-strength one-line change for a host
# with less memory to spare. Measured in KiB, so 47104 is 46 MiB.
_MEMORY_COST = 47104
_TIME_COST = 1
_PARALLELISM = 1

# A hash of a value nobody has, standing in for the password of an account that has none,
# so that both an unknown username and a `NULL` password_hash cost the same to reject as
# a wrong password does to reject. Skipping the work is what makes either one a free
# oracle for anyone who can guess a username.
#
# It is written out rather than computed on import, and it is hashed with the parameters
# above: a cheaper dummy reintroduces the timing difference it exists to remove. A test
# asserts its parameters, so lowering the constants above fails that test rather than
# quietly weakening the control.
#
# It is deliberately *not* peppered, unlike a real hash. Argon2id costs the same whatever
# it is given, so equalising what a rejection costs does not require equalising the secret
# in front of it, and leaving this a constant means the control does not change shape when
# the pepper does. Nobody can sign in with it either: the verification path peppers its
# input like any other, so no guess reaches a match.
DUMMY_HASH = "$argon2id$v=19$m=47104,t=1,p=1$og7a9wFXIS2wJZlEdKpqgw$ACCclBidLZt1xjz139/ewCmH4R9WbjL4EcTWJkifh8k"

_HASHER = PasswordHasher(
    time_cost=_TIME_COST,
    memory_cost=_MEMORY_COST,
    parallelism=_PARALLELISM,
)

# Argon2 has no pepper parameter of its own, so the secret is keyed into the password with
# HMAC before Argon2 ever sees it. HMAC rather than concatenation, so that no two
# (pepper, password) pairs can produce the same input, and so the pepper is not recoverable
# from the hash even if the scheme were changed to be reversible.
_PEPPER_CONTEXT = b"dockb password pepper v1:"


def pepper_from(secret: str) -> bytes:
    """Derive the password pepper from the server secret.

    Domain-separated from everything else made from that secret — ``TokenEncryptor`` takes
    ``sha256(secret)`` outright — so that the pepper is not the same bytes as the token
    encryption key, and so that the two can be rotated independently.

    Refuses an empty secret. HMAC accepts an empty key and quietly becomes an unkeyed hash,
    so a ``DOCKB_SECRET_KEY`` that is set but blank would silently drop the protection this
    exists to add, and still produce hashes that look fine. That is a loud failure here
    instead.
    """
    if not secret.strip():
        raise ValueError("the server secret is empty, so there is no pepper to derive")
    return hashlib.sha256(_PEPPER_CONTEXT + secret.encode("utf-8")).digest()


class PasswordPolicyError(Exception):
    """A password the policy refuses, carrying the reason to show the person.

    One error rather than several because the callers render it differently — the CLI to
    stderr, the route as a client error — and neither should have to work out which rule
    was broken.
    """


def hash_password(pepper: bytes, password: str, *, generated: bool = False) -> str:
    """Check *password* against the policy and return its Argon2id hash.

    The policy is enforced here rather than beside it, so that this is the only way to
    get a hash and no caller can put a rejected password in the store by forgetting to
    ask. *generated* exempts the minimum length, because a value from ``secrets`` is
    trusted on the strength of how it was made rather than how long it is; the maximum
    still applies.

    *pepper* is the value from :func:`pepper_from`. It is not stored: it is the same on
    every machine that shares a secret, so changing it invalidates every password at once.
    """
    _check_policy(password, generated=generated)
    return _HASHER.hash(_keyed(pepper, password))


def verify_password(pepper: bytes, password: str, stored: str | None) -> bool:
    """Return whether *password* is the one *stored* holds.

    A ``None`` *stored* is verified against :data:`DUMMY_HASH`, so a provider-only row
    with no password costs the same to reject as a wrong one.

    The policy is deliberately not applied here. A stored password was accepted when it
    was hashed, and whether it still satisfies today's policy is not what decides whether
    it matches.
    """
    try:
        return _HASHER.verify(stored or DUMMY_HASH, _keyed(pepper, password))
    except (InvalidHashError, VerificationError):
        # A mismatch, or a `password_hash` that did not come out of argon2 — a corrupted
        # column, or a value written by something else. Both are a refusal to sign in,
        # never an error the caller should have to handle separately, and least of all a
        # 500 on the login route. `InvalidHashError` is a ValueError and `VerificationError`
        # is not, so they have to be caught together by name.
        return False


def _keyed(pepper: bytes, password: str) -> bytes:
    """Return what Argon2id actually hashes: the password under *pepper*.

    HMAC-SHA256, keyed by the pepper. This is the whole of the pepper's effect: an attacker
    holding a stolen ``dockb_app.db`` cannot hash a guess, because they cannot compute this
    value without the server secret, and so the cost of each guess moves from their machine
    to one that has to have survived here.
    """
    return hmac.new(pepper, password.encode("utf-8"), hashlib.sha256).digest()


def _check_policy(password: str, *, generated: bool) -> None:
    """Raise ``PasswordPolicyError`` unless *password* is one DockB will store.

    The maximum is checked first and, more importantly, checked before any hashing: it is
    there to bound the cost of a single Argon2id operation, which a check placed after
    the hashing would not do at all.

    The generated exemption covers the *minimum* only. An empty value is refused outright,
    because a password of nothing is not a credential however it was arrived at, and
    exempting it would leave ``hash_password("", generated=True)`` able to fill the column.
    """
    length = len(password)
    if length > MAXIMUM_LENGTH:
        raise PasswordPolicyError(f"a password may be at most {MAXIMUM_LENGTH} characters")
    if length == 0:
        raise PasswordPolicyError("a password may not be empty")
    if not generated and length < MINIMUM_LENGTH:
        raise PasswordPolicyError(f"a password must be at least {MINIMUM_LENGTH} characters")
