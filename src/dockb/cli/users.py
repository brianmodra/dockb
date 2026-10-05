"""``dockb users`` — the admin-only account tool.

Accounts are created, and passwords reset, here and nowhere else. There is no
self-registration and no recovery flow over HTTP, so this command is the only
route to a new account and the only route back into a lost one. That is a
deliberate fit for a small, known user set; see ``README_auth.md`` §7.

Every command that generates a password prints it **once**, on stdout, and never
logs it. No command accepts one as an argument, because an argument is recorded in
the shell history and the process table.

None of these commands reach into a running server. ``block``, ``delete`` and
``set-password`` end a live session by stamping ``credentials_changed_at``, which
the server compares on its next request — this process cannot evict an in-memory
session it does not own.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

from dockb.composition import resolve_document_base_dir
from dockb.infrastructure.accounts.store import (
    AccountStore,
    EmailTakenError,
    UnknownUserError,
    UsernameTakenError,
    normalize_username,
)
from dockb.passwords import hash_password, pepper_from

# Enough entropy to be unguessable, and short enough to read aloud. The policy
# minimum is deliberately not applied here: this value's strength comes from
# generation, not from somebody choosing it, and the first thing its holder does is
# replace it with one they chose.
_TEMPORARY_PASSWORD_BYTES = 18

_EXIT_OK = 0
_EXIT_ERROR = 1


# The handlers are plain functions rather than argparse actions, so what one needs
# beyond its own arguments arrives as this one object instead of being threaded
# through argparse.


@dataclass(frozen=True)
class _Admin:
    """The store and the pepper derived from the same secret that built it.

    Holding the pepper rather than re-deriving it per command keeps the hash written
    by this process verifiable by the server: both come from ``DOCKB_SECRET_KEY``, and
    a hash keyed with anything else produces an account nobody can sign in to.
    """

    store: AccountStore
    pepper: bytes


class MissingConfigurationError(Exception):
    """A required setting is absent, so the command cannot start."""


def _fail(message: str) -> int:
    """Report *message* on stderr and return the failure exit code.

    Everything this tool refuses goes through here, so a refusal is always one
    ``error:`` line on stderr and a nonzero exit — never a traceback, and never a
    password.
    """
    print(f"error: {message}", file=sys.stderr)
    return _EXIT_ERROR


def _temporary_password() -> str:
    """Return a fresh high-entropy temporary password."""
    return secrets.token_urlsafe(_TEMPORARY_PASSWORD_BYTES)


def _resolve() -> _Admin:
    """Build the store the *server* would use, or report what is missing.

    ``resolve_document_base_dir`` is the server's own rule, so this cannot end up
    administering a different database than the one serving requests.
    ``DOCKB_SECRET_KEY`` is required for the same reason it is on the server: it
    peppers the password hash, and one keyed differently would not verify.
    """
    secret = os.environ.get("DOCKB_SECRET_KEY", "")
    # Stripped, not merely tested for truth: a whitespace secret is truthy, and would
    # be a weak key for every credential it touches.
    if not secret.strip():
        raise MissingConfigurationError("DOCKB_SECRET_KEY must be set in the environment or a .env file")
    return _Admin(
        store=AccountStore(base_dir=resolve_document_base_dir(), secret=secret),
        pepper=pepper_from(secret),
    )


def _refusal(exc: Exception, admin: _Admin, args: argparse.Namespace) -> str:
    """Describe a refused create, naming the value that collided and the next step.

    A soft delete keeps the row, so the username stays taken. An admin retrying a
    create then needs to know whether somebody deleted that account or a different
    person already holds the name — the two have different next commands. The address
    is echoed because an administrator supplied it on the command line and may have
    several accounts to hold it against.
    """
    if isinstance(exc, EmailTakenError):
        return f"email {args.email!r} is already in use by another account"
    if isinstance(exc, UsernameTakenError):
        username = normalize_username(args.username)
        row = admin.store.get_user(username)
        if row is not None and row.get("deleted_at"):
            return f"username {username!r} is taken by a deleted account; use 'undelete' to restore it"
    return str(exc)


def _cmd_create(admin: _Admin, args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    temporary = _temporary_password()
    try:
        admin.store.create_user(
            args.username,
            email=args.email,
            display_name=args.display_name or username,
            password_hash=hash_password(admin.pepper, temporary, generated=True),
            must_change_password=True,
        )
    except (UsernameTakenError, EmailTakenError) as exc:
        return _fail(_refusal(exc, admin, args))
    print(f"created {username}")
    print(temporary)
    return _EXIT_OK


def _cmd_list(admin: _Admin, _args: argparse.Namespace) -> int:
    users = admin.store.list_users()
    if not users:
        print("no accounts")
        return _EXIT_OK
    for user in users:
        states = [state for state in ("blocked", "deleted") if user.get(f"{state}_at")]
        if user.get("must_change_password"):
            states.append("must change password")
        print(f"{user['username']}\t{user['email'] or '-'}\t{', '.join(states) or 'active'}")
    return _EXIT_OK


def _cmd_set_password(admin: _Admin, args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    temporary = _temporary_password()
    admin.store.set_password_hash(username, hash_password(admin.pepper, temporary, generated=True), must_change_password=True)
    print(f"reset password for {username}")
    print(temporary)
    return _EXIT_OK


def _cmd_block(admin: _Admin, args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    admin.store.block_user(username)
    print(f"blocked {username}")
    return _EXIT_OK


def _cmd_unblock(admin: _Admin, args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    admin.store.unblock_user(username)
    print(f"unblocked {username}")
    return _EXIT_OK


def _cmd_delete(admin: _Admin, args: argparse.Namespace) -> int:
    if not args.yes:
        return _fail("delete refuses logins and ends live sessions; re-run with --yes to confirm")
    username = normalize_username(args.username)
    admin.store.soft_delete_user(username)
    print(f"deleted {username}")
    return _EXIT_OK


def _cmd_undelete(admin: _Admin, args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    admin.store.restore_user(username)
    print(f"restored {username}")
    return _EXIT_OK


_HANDLERS = {
    "create": _cmd_create,
    "list": _cmd_list,
    "set-password": _cmd_set_password,
    "block": _cmd_block,
    "unblock": _cmd_unblock,
    "delete": _cmd_delete,
    "undelete": _cmd_undelete,
}


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for ``users <command>``."""
    parser = argparse.ArgumentParser(prog="dockb users", description=__doc__.split("\n\n", maxsplit=1)[0])
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create an account with a temporary password")
    create.add_argument("--username", required=True, help="the account's name; stored lowercased")
    create.add_argument("--email", required=True, help="an unverified address; must be unique")
    create.add_argument("--display-name", default=None, help="defaults to the username")

    commands.add_parser("list", help="every account and its state; never prints a password")

    for name, help_text in (
        ("block", "refuse logins and end live sessions"),
        ("unblock", "reverse a block"),
        ("delete", "soft delete: refuse logins and end sessions"),
        ("undelete", "clear a soft delete, leaving credentials alone"),
        ("set-password", "re-issue a temporary password and require a change"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("username", help="the account; matched case-insensitively")
        if name == "delete":
            sub.add_argument("--yes", action="store_true", help="confirm the delete")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command. Returns the process exit code.

    Usage errors come back as 2 and refusals as 1, which is the usual Unix split: the
    first is a malformed command line, the second a command that ran and declined.
    argparse raises rather than returning, so it is caught here to keep ``main`` total.
    """
    load_dotenv()
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)
    try:
        admin = _resolve()
    except MissingConfigurationError as exc:
        return _fail(str(exc))
    try:
        return _HANDLERS[args.command](admin, args)
    except (UsernameTakenError, EmailTakenError, UnknownUserError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
