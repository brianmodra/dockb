"""Reconstruct a chapter from the knowledge graph as markdown, from the shell.

Run with ``python -m dockb.cli.reconstruct_chapter <chapter_id> [--out PATH]``.
Without ``--out`` the chapter is written into the server-owned markdown tree
(``<base>/<document title>/<Act X>/<chapter title>.md`` under
``DOCKB_CHAPTERS_DIR``, defaulting to ``cwd/dockb_chapters_dir``) and
git-committed; ``--out`` writes the exact path given instead. The Neo4j
connection comes from ``NEO4J_URL``, ``NEO4J_USER`` and ``NEO4J_PASSWORD``
(or a ``.env`` file, exactly as the API server reads them). A missing variable or model
is reported as a single ``error:`` line and exit 1, not a traceback — see ``startup.py``.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

from dotenv import load_dotenv

from dockb.cli.startup import (
    MissingConfigurationError,
    UnknownUserError,
    account_id_for,
    load_spacy_model,
    neo4j_settings,
)
from dockb.composition import resolve_document_base_dir
from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.document_store import DocumentStore
from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.markdown_export import reconstruct_chapter_file, reconstruct_chapter_to_store


def main(argv: list[str] | None = None) -> int:
    """Reconstruct a single chapter from the graph, writing to the store tree or a file."""
    parser = argparse.ArgumentParser(prog="dockb reconstruct-chapter", description=__doc__)
    parser.add_argument("chapter_id", help="id of the chapter to reconstruct")
    parser.add_argument("-o", "--out", type=Path, default=None, help="write the markdown to PATH instead of the store tree")
    parser.add_argument(
        "--owner",
        default=None,
        help="username owning the chapter's document (required unless --out is given)",
    )
    args = parser.parse_args(argv)

    if args.out is None and not args.owner:
        print("error: --owner is required without --out: the store tree is per-account", file=sys.stderr)
        return 1

    load_dotenv()
    try:
        settings = neo4j_settings()
        nlp = load_spacy_model()
    except MissingConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    session_factory = SessionFactory(
        uri=settings["NEO4J_URL"],
        user=settings["NEO4J_USER"],
        password=settings["NEO4J_PASSWORD"],
    )
    with ExitStack() as stack:
        session = stack.enter_context(session_factory.session())
        chapter_repo = ChapterRepository(session)
        document_repo = DocumentRepository(session)
        try:
            if args.out is not None:
                reconstruct_chapter_file(args.chapter_id, chapter_repo, args.out, nlp)
                return 0
            store = DocumentStore(base_dir=resolve_document_base_dir(), account_id=account_id_for(args.owner or ""))
            path = reconstruct_chapter_to_store(args.chapter_id, chapter_repo, document_repo, store, nlp)
            print(path)
        except UnknownUserError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except ChapterMismatchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            session_factory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
