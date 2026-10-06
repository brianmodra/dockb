"""``dockb users`` — the admin-only account tool.

Accounts are created, and passwords reset, here and nowhere else. There is no
self-registration and no recovery flow over HTTP, so this command is the only
route to a new account and the only route back into a lost one. That is a
deliberate fit for a small, known user set; see ``README_auth.md`` §7.

``assign`` is here for the same reason, and it is the only command in DockB that
moves a document between accounts: a manuscript created before accounts owned
documents, or one whose account was deleted, is in nobody's library and cannot be
reached over HTTP at all. There is no transfer control in the editor, so this
command is the whole of the ownership-transfer surface. It is also the only
subcommand that reaches the knowledge graph, and so the only one that needs the
Neo4j settings — the other seven need only ``DOCKB_SECRET_KEY``.

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

from dockb.cli.startup import MissingConfigurationError, neo4j_settings
from dockb.composition import resolve_document_base_dir
from dockb.exceptions import DocumentFormatError, DocumentNotFoundError, DuplicateTitleError, SnapshotError
from dockb.infrastructure.accounts.store import (
    AccountStore,
    EmailTakenError,
    UnknownUserError,
    UsernameTakenError,
    normalize_username,
)
from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.passwords import hash_password, pepper_from
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.assignment_service import Assignment, DocumentAssignmentService

# Enough entropy to be unguessable, and short enough to read aloud. The policy
# minimum is deliberately not applied here: this value's strength comes from
# generation, not from somebody choosing it, and the first thing its holder does is
# replace it with one they chose.
_TEMPORARY_PASSWORD_BYTES = 18

_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_USAGE = 2


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


def _fail(message: str) -> int:
    """Report *message* on stderr and return the failure exit code.

    Everything this tool refuses goes through here, so a refusal is always one
    ``error:`` line on stderr and a nonzero exit — never a traceback, and never a
    password.
    """
    print(f"error: {message}", file=sys.stderr)
    return _EXIT_ERROR


def _fail_usage(message: str) -> int:
    """Report a malformed command line and exit 2, as argparse's own errors do.

    Distinct from :func:`_fail` because a command that ran and declined is a different
    thing from one that was never a valid command, and a script wants to tell them apart.
    """
    print(f"error: {message}", file=sys.stderr)
    return _EXIT_USAGE


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


def _cmd_assign(admin: _Admin, args: argparse.Namespace) -> int:
    # Not a refusal but a malformed command line, so it exits like argparse's own usage
    # errors rather than like a command that ran and declined.
    if args.all_to is None and args.username is None:
        return _fail_usage(
            "assign needs a username: " + "'dockb users assign <document-id> <username>' or 'dockb users assign --all-to <username>'"
        )
    username = args.all_to if args.all_to is not None else args.username
    account_id = _destination_account(admin, username)
    if account_id is None:
        return _EXIT_ERROR
    return _assign_documents(args, account_id)


def _destination_account(admin: _Admin, username: str) -> str | None:
    """Return the account id a document may be assigned to, or None after reporting why not.

    Two refusals, both about the account rather than the document: a username nobody
    holds, and one held by a soft-deleted account. The second is the point of the check —
    a soft-deleted account cannot sign in, so a manuscript assigned to it would be
    unreachable over HTTP again, which is the condition this command exists to end. A
    *blocked* account is a valid destination: blocking is about logins and is reversible.
    Reports through ``_fail`` and returns None so the caller has one exit path.
    """
    normalized = normalize_username(username)
    row = admin.store.get_user(normalized)
    if row is None:
        _fail(f"unknown user {normalized!r}")
        return None
    if row.get("deleted_at"):
        _fail(f"user {normalized!r} is deleted; run 'dockb users undelete {normalized}' before assigning a document to it")
        return None
    return str(row["id"])


def _assign_documents(args: argparse.Namespace, account_id: str) -> int:
    """Assign the named document, or every unowned one, to *account_id*.

    ``--all-to`` reports each document it moved and keeps going past a refusal, so one
    title clash does not strand the rest of a library; the exit code is 1 if anything was
    refused, which is what tells a script the run was not complete.
    """
    try:
        settings = neo4j_settings()
    except MissingConfigurationError as exc:
        return _fail(str(exc))
    session_factory = SessionFactory(uri=settings["NEO4J_URL"], user=settings["NEO4J_USER"], password=settings["NEO4J_PASSWORD"])
    try:
        with session_factory.session() as session:
            document_repo = DocumentRepository(session)
            service = DocumentAssignmentService(document_repo, DocumentStoreFactory(resolve_document_base_dir()))
            if args.all_to:
                return _assign_unowned(service, document_repo, account_id, args.yes)
            return _assign_one(service, args.document_id, account_id)
    finally:
        session_factory.close()


def _assign_one(service: DocumentAssignmentService, document_id: str, account_id: str) -> int:
    try:
        assignment = service.assign(document_id, account_id)
    except (DocumentFormatError, DocumentNotFoundError, DuplicateTitleError, SnapshotError) as exc:
        return _fail(str(exc))
    _report(assignment)
    return _EXIT_OK


def _assign_unowned(
    service: DocumentAssignmentService,
    document_repo: DocumentRepository,
    account_id: str,
    confirmed: bool,
) -> int:
    unowned = document_repo.list_unowned()
    if not unowned:
        print("every document already belongs to an account")
        return _EXIT_OK
    if not confirmed:
        return _fail(f"{len(unowned)} document(s) have no owner; re-run with --yes to assign them all")
    failures = 0
    for row in unowned:
        try:
            assignment = service.assign(str(row["id"]), account_id)
        except (DocumentFormatError, DocumentNotFoundError, DuplicateTitleError, SnapshotError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue
        _report(assignment)
    if failures:
        print(f"error: {failures} of {len(unowned)} document(s) were not assigned", file=sys.stderr)
        return _EXIT_ERROR
    return _EXIT_OK


def _report(assignment: Assignment) -> None:
    """Print what one assignment did."""
    if assignment.already_owned:
        print(f"{assignment.document_id} ({assignment.title}) already belongs to this account")
        return
    moved = "with its markdown tree" if assignment.tree_moved else "no markdown tree on disk"
    print(f"assigned {assignment.document_id} ({assignment.title}) to this account, {moved}")


_HANDLERS = {
    "create": _cmd_create,
    "list": _cmd_list,
    "set-password": _cmd_set_password,
    "block": _cmd_block,
    "unblock": _cmd_unblock,
    "delete": _cmd_delete,
    "undelete": _cmd_undelete,
    "assign": _cmd_assign,
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

    assign = commands.add_parser("assign", help="give a document, or every unowned document, to an account")
    target = assign.add_mutually_exclusive_group(required=True)
    target.add_argument("document_id", nargs="?", help="the document to give, by id")
    target.add_argument("--all-to", metavar="username", default=None, help="give every document that belongs to no account")
    assign.add_argument("username", nargs="?", help="the account receiving the document; not needed with --all-to")
    assign.add_argument("--yes", action="store_true", help="confirm --all-to, which moves every unowned document at once")

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
