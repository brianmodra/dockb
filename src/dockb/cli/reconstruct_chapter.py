"""Reconstruct a chapter from the knowledge graph as markdown, from the shell.

Run with ``python -m dockb.cli.reconstruct_chapter <chapter_id> [--out PATH]``.
Without ``--out`` the reconstructed markdown is printed to stdout. The Neo4j
connection comes from ``NEO4J_URL``, ``NEO4J_USER`` and ``NEO4J_PASSWORD``
(or a ``.env`` file, exactly as the API server reads them).
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import ExitStack
from pathlib import Path

import spacy
from dotenv import load_dotenv

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.services.markdown_export import reconstruct_chapter_file, reconstruct_chapter_markdown


def main(argv: list[str] | None = None) -> int:
    """Reconstruct a single chapter from the graph, writing markdown to stdout or a file."""
    parser = argparse.ArgumentParser(prog="dockb reconstruct-chapter", description=__doc__)
    parser.add_argument("chapter_id", help="id of the chapter to reconstruct")
    parser.add_argument("-o", "--out", type=Path, default=None, help="write the markdown to PATH instead of stdout")
    args = parser.parse_args(argv)

    load_dotenv()
    session_factory = SessionFactory(
        uri=os.environ["NEO4J_URL"],
        user=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    nlp = spacy.load("en_core_web_sm")
    with ExitStack() as stack:
        session = stack.enter_context(session_factory.session())
        chapter_repo = ChapterRepository(session)
        try:
            if args.out is not None:
                reconstruct_chapter_file(args.chapter_id, chapter_repo, args.out, nlp)
                return 0
            print(reconstruct_chapter_markdown(args.chapter_id, chapter_repo, nlp), end="")
        except ChapterMismatchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            session_factory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
