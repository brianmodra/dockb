# tests/conftest.py
import logging

import pytest
import spacy


@pytest.fixture(scope="session", autouse=True)
def set_test_logging():
    # Force the root logger to DEBUG level for the entire test session
    logging.getLogger().setLevel(logging.DEBUG)

    # Optional: If you use a specific named logger in your app, change it here:
    # logging.getLogger("your_app_name").setLevel(logging.DEBUG)


@pytest.fixture(scope="session")
def nlp():
    return spacy.load("en_core_web_sm")


@pytest.fixture
def document():
    from dockb.models.document import Document

    return Document()


@pytest.fixture
def chapter():
    from dockb.models.chapter import Chapter

    return Chapter()


@pytest.fixture
def paragraph():
    from dockb.models.paragraph import Paragraph

    return Paragraph()


@pytest.fixture
def sentence():
    from dockb.models.sentence import Sentence

    return Sentence()


@pytest.fixture
def token():
    from dockb.models.token import Token

    return Token()
