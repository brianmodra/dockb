"""The ``dockb`` command: one entry point for every DockB command-line tool.

DockB has three of them — importing a manuscript, writing a chapter back out, and
administering accounts — and they were three separate modules reachable only by
``python -m``. Each already named itself ``dockb <command>`` in its usage text, which
promised a command that did not exist. This is it: ``dockb <command> ...``, with
``users`` nested because its six subcommands need namespacing and the other two are a
single verb each.

Every command's own ``main(argv)`` still works, so ``python -m dockb.cli.users`` and
``dockb users`` are the same program and cannot drift apart.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from dockb.cli import import_document, reconstruct_chapter, users

_COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "import-document": import_document.main,
    "reconstruct-chapter": reconstruct_chapter.main,
    "users": users.main,
}

_SUMMARIES = {
    "import-document": "walk a directory of markdown and update the knowledge graph",
    "reconstruct-chapter": "write one chapter back out as markdown",
    "users": "administer accounts",
}


def _usage() -> str:
    """Return the one-screen help listing every command and what it does."""
    width = max(len(name) for name in _COMMANDS)
    lines = ["usage: dockb <command> [options]", "", "commands:"]
    lines += [f"  {name.ljust(width)}  {_SUMMARIES[name]}" for name in sorted(_COMMANDS)]
    lines += ["", "Run 'dockb <command> --help' for a command's own options."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Dispatch to a command's own ``main``, returning its exit code.

    Returns 2 for a missing or unknown command, matching the exit code a command uses
    for a malformed command line: ``dockb typo`` is argparse's kind of error, not a
    command that ran and declined.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in _COMMANDS:
        return _COMMANDS[arguments[0]](arguments[1:])
    print(_usage(), file=sys.stderr)
    return 2
