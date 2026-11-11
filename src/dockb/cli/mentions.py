"""The mentions sweep CLI: backfill a document's mention verdicts.

``dockb mentions sweep <document-title-or-id>`` evaluates the paragraphs whose
verdicts are missing (state 1: never evaluated) or stale (state 4: invalidated
by a text or identity change), stamping each as it is judged — so an
interrupted sweep resumes by simply running again. ``--full`` instead
re-evaluates every paragraph from nothing, ignoring existing MENTIONS.

The sweep is a manual, operator-run job: it never runs at startup and is
never automatic. The per-save evaluation is the MentionsJob; see
``src/dockb/services/README_mentions.md``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import ExitStack
from pathlib import Path

from dotenv import load_dotenv

from dockb.cli.import_document import account_id_for
from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.mentions_repository import MentionsRepository
from dockb.services.mentions import evaluate_chapter_tier1, evaluate_chapter_tier2

_STATE_NAMES = {1: "never evaluated", 2: "no mentions", 3: "mentions", 4: "stale"}

_SWEEP_SUMMARY = "evaluate the document's pending mention verdicts"

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """The mentions CLI's parser: one verb, described wherever help appears."""
    parser = argparse.ArgumentParser(prog="dockb mentions", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sweep = sub.add_parser(
        "sweep",
        help=_SWEEP_SUMMARY,
        description=(
            "Evaluate one document's paragraphs whose mention verdict is missing"
            " (state 1) or stale (state 4) — the characters a paragraph names, first"
            " by name matching (tier 1), then by an LLM pass over the candidates tier"
            " 1 left pending (tier 2). Each verdict is stamped as it is judged, so an"
            " interrupted sweep resumes by running again."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "States: 1 never evaluated, 2 judged - no mentions, 3 judged - mentions found,"
            " 4 stale (the paragraph's text or a character's identity changed after the last judgement).\n"
            "examples:\n"
            "  dockb mentions sweep Linchpin --owner brian            # by document title\n"
            "  dockb mentions sweep d1 --owner brian --full           # by id, re-evaluate everything\n"
            "  dockb mentions sweep Linchpin --owner brian --no-ai    # tier 1 only, no model calls"
        ),
    )
    sweep.add_argument("document", help="the document's id, or its title")
    sweep.add_argument(
        "--owner",
        required=True,
        help="the account the document belongs to, as its username or user id",
    )
    sweep.add_argument(
        "--full",
        action="store_true",
        help="re-evaluate every paragraph, ignoring existing MENTIONS",
    )
    sweep.add_argument(
        "--no-ai",
        action="store_true",
        help="when the pipeline would call the model, log a warning and leave those candidates un-evaluated",
    )
    return parser


def _choice_summary(parser: argparse.ArgumentParser) -> str:
    """A stderr block listing the choices a bad command line could have made."""
    sub = parser._subparsers._group_actions[0]  # type: ignore[union-attr]  # pylint: disable=protected-access
    choices = list(getattr(sub, "_choices_actions", []))
    width = max((len(str(action.metavar or action.dest)) for action in choices), default=0)
    lines = ["", "commands:"]
    lines += [f"  {str(action.metavar or action.dest).ljust(width)}  {action.help}" for action in choices]
    for name, child in sub.choices.items():  # type: ignore[union-attr]  # pylint: disable=protected-access
        lines += ["", f"options for '{name}':", *_option_summary(child)]
    lines += ["", "Run 'dockb mentions <command> --help' for a command's own options."]
    return "\n".join(lines)


def _option_summary(child: argparse.ArgumentParser) -> list[str]:
    """The child command's flags, aligned, with what each is for."""
    lines: list[str] = []
    width = 0
    entries: list[tuple[str, str | None]] = []
    for option in child._actions:  # argparse internals  # pylint: disable=protected-access
        if option.dest == "help" or not option.option_strings:
            continue
        flags = ", ".join(option.option_strings)
        label = option.metavar or (option.dest.upper() if option.const is None else None)
        text = f"  {flags + ((' ' + str(label)) if label else '')}"
        entries.append((text, option.help))
        width = max(width, len(text))
    lines += [f"{text.ljust(width)}  {gloss}" for text, gloss in entries]
    return lines


def _build(stack: ExitStack) -> tuple[ChapterRepository, DocumentRepository, MentionsRepository]:
    """The repositories the sweep reads and writes through, in its own session.

    The session is entered on the caller's stack, so it stays open for the whole
    sweep and closes (with the connection pool) when the caller's ``with``
    unwinds — not when this function returns.
    """
    repo_root = Path(__file__).resolve().parents[3]
    load_dotenv(repo_root / ".env")
    load_dotenv()
    session_factory = SessionFactory(
        uri=os.environ["NEO4J_URL"],
        user=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    stack.callback(session_factory.close)
    session = stack.enter_context(session_factory.session())
    return ChapterRepository(session), DocumentRepository(session), MentionsRepository(session)


def _log_chapter_mentions(
    chapter: Chapter,
    *,
    owner: str,
    mentions_repo: MentionsRepository,
    document: Document,
) -> None:
    """Log each mention (character, chapter title, paragraph index) and the chapter's summary."""
    characters = {c.id: c.title for c in document.chapters if c.category == "Character"}
    counts: dict[str, int] = {}
    for state in mentions_repo.paragraph_states(owner, chapter_id=chapter.id):
        raw_mentions = state.get("mentions")
        mentions: list[str] = [str(character_id) for character_id in raw_mentions] if isinstance(raw_mentions, list) else []
        index = int(state.get("index") or 0)
        for character_id in mentions:
            title = characters.get(character_id, character_id)
            logger.info(
                "Character '%s' mentioned in chapter '%s', paragraph %d",
                title,
                chapter.title,
                index,
            )
            counts[title] = counts.get(title, 0) + 1
    if counts:
        summary = ", ".join(f"'{title}' x {count}" for title, count in sorted(counts.items()))
        logger.info("Chapter '%s' mentions summary: %s", chapter.title, summary)
    else:
        logger.info("Chapter '%s' mentions summary: none", chapter.title)


def _resolve_document(document_ref: str, owner: str, document_repo: DocumentRepository) -> str | None:
    """The document id for *document_ref* — an id when it loads, else a title match."""
    document = document_repo.load(document_ref, owner)
    if document is not None:
        return document_ref
    for summary in document_repo.list_all(owner):
        if summary["title"].lower() == document_ref.lower():
            return str(summary["id"])
    return None


def main(argv: list[str] | None = None) -> int:  # pylint: disable=too-many-locals
    """Run the sweep over one document, printing the per-chapter state counts."""
    parser = _build_parser()
    if argv and argv[0] == "help":
        parser.print_help()
        sub = parser._subparsers._group_actions[0]  # type: ignore[union-attr]  # pylint: disable=protected-access
        for name, child in sub.choices.items():  # type: ignore[union-attr]  # pylint: disable=protected-access
            options = _option_summary(child)
            if options:
                print(f"\noptions for '{name}':")
                print("\n".join(options))
        return 0
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_error:
        code = exit_error.code if isinstance(exit_error.code, int) else 2
        if code == 2:
            # argparse only says which choices exist; say what they are for
            print(_choice_summary(parser), file=sys.stderr)
        return code
    except argparse.ArgumentError as error:
        # a subparser's bad command line surfaces here rather than as an exit
        print(f"{parser.prog}: error: {error}", file=sys.stderr)
        print(_choice_summary(parser), file=sys.stderr)
        return 2

    owner = account_id_for(args.owner)
    with ExitStack() as stack:
        chapter_repo, document_repo, mentions_repo = _build(stack)

        document_id = _resolve_document(args.document, owner, document_repo)
        if document_id is None:
            print(f"error: no document '{args.document}' for that account", file=sys.stderr)
            return 1

        document = document_repo.load(document_id, owner)
        assert document is not None

        for chapter in document.chapters:
            states = mentions_repo.paragraph_states(owner, chapter_id=chapter.id)
            counts = {state: sum(1 for row in states if row["state"] == state) for state in (1, 2, 3, 4)}
            before = " ".join(f"state {state} ({_STATE_NAMES[state]}): {counts[state]}" for state in (1, 2, 3, 4))
            print(f"{chapter.title}: {before}")

            if args.full:
                mentions_repo.reset(owner, chapter_id=chapter.id)
            evaluate_chapter_tier1(
                chapter.id,
                owner=owner,
                mentions_repo=mentions_repo,
                chapter_repo=chapter_repo,
            )
            evaluate_chapter_tier2(
                chapter.id,
                owner=owner,
                mentions_repo=mentions_repo,
                chapter_repo=chapter_repo,
                no_ai=args.no_ai,
            )
            _log_chapter_mentions(chapter, owner=owner, mentions_repo=mentions_repo, document=document)

            after_rows = mentions_repo.paragraph_states(owner, chapter_id=chapter.id)
            pending = sum(1 for row in after_rows if row["state"] in (1, 4))
            print(f"{chapter.title}: pending after sweep: {pending}")

        remaining = mentions_repo.paragraph_states(owner, document_id=document_id)
        pending = sum(1 for row in remaining if row["state"] in (1, 4))
        if pending:
            print(f"{pending} paragraph(s) still pending (an LLM outage leaves them for the next sweep)")
        else:
            print("every paragraph's mention verdicts are settled")
        return 0
