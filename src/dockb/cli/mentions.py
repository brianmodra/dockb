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

logger = logging.getLogger(__name__)


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
    parser = argparse.ArgumentParser(prog="dockb mentions", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sweep = sub.add_parser("sweep", help="evaluate the document's pending mention verdicts")
    sweep.add_argument("document", help="the document's id, or its title")
    sweep.add_argument("--owner", required=True, help="the account the document belongs to, as its username or user id")
    sweep.add_argument("--full", action="store_true", help="re-evaluate every paragraph, ignoring existing MENTIONS")
    sweep.add_argument(
        "--no-ai",
        action="store_true",
        help="when the pipeline would call the model, log a warning and leave those candidates un-evaluated",
    )
    args = parser.parse_args(argv)

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
                document_repo=document_repo,
            )
            evaluate_chapter_tier2(
                chapter.id,
                owner=owner,
                mentions_repo=mentions_repo,
                chapter_repo=chapter_repo,
                document_repo=document_repo,
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
