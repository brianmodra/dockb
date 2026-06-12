"""Fixtures for repository tests."""

from unittest.mock import MagicMock

import pytest
from neo4j import Session


@pytest.fixture
def neo4j_session():
    """Mocked Neo4j Session whose run() returns a generic MagicMock."""
    session = MagicMock(spec=Session)
    session.run.return_value = MagicMock()
    return session


@pytest.fixture
def repo(neo4j_session):
    """SentenceRepository backed by the mocked session."""
    from dockb.repositories.sentence_repository import SentenceRepository

    return SentenceRepository(neo4j_session)


@pytest.fixture
def paragraph_repo(neo4j_session):
    """ParagraphRepository backed by the mocked session."""
    from dockb.repositories.paragraph_repository import ParagraphRepository

    return ParagraphRepository(neo4j_session)


@pytest.fixture
def chapter_repo(neo4j_session):
    """ChapterRepository backed by the mocked session."""
    from dockb.repositories.chapter_repository import ChapterRepository

    return ChapterRepository(neo4j_session)


@pytest.fixture
def document_repo(neo4j_session):
    """DocumentRepository backed by the mocked session."""
    from dockb.repositories.document_repository import DocumentRepository

    return DocumentRepository(neo4j_session)
