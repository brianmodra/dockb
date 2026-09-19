"""Import a document directory into the knowledge graph, from the shell.

Run with ``python -m dockb.cli.import_document <document_dir>``. The Neo4j
connection comes from ``NEO4J_URL``, ``NEO4J_USER`` and ``NEO4J_PASSWORD``
(or a ``.env`` file, exactly as the API server reads them).
"""

from __future__ import annotations

import argparse
import getpass
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import spacy
from dotenv import load_dotenv

from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.markdown_import import import_document_directory


def main(argv: list[str] | None = None) -> int:
    """Import *document_dir* into the graph, printing one line per chapter file."""
    parser = argparse.ArgumentParser(prog="dockb import-document", description=__doc__)
    parser.add_argument("document_dir", type=Path, help="directory of markdown chapter files")
    args = parser.parse_args(argv)

    load_dotenv()
    session_factory = SessionFactory(
        uri=os.environ["NEO4J_URL"],
        user=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    with ExitStack() as stack:
        session = stack.enter_context(session_factory.session())
        repos: dict[type, Any] = {
            Document: DocumentRepository(session),
            Chapter: ChapterRepository(session),
            Paragraph: ParagraphRepository(session),
            Sentence: SentenceRepository(session),
        }
        uow_factory = UnitOfWorkFactory(repos=repos, session_factory=session_factory, reconstructor=None)
        summaries = import_document_directory(
            args.document_dir,
            getpass.getuser(),
            spacy.load("en_core_web_sm"),
            repos[Document],
            repos[Chapter],
            uow_factory,
        )
        session_factory.close()
    for summary in summaries:
        verb = "imported" if summary.created else "synced"
        print(f"{summary.chapter_id} {verb}: {summary.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
