"""Fixtures for integration tests that require a real Neo4j database."""

import logging
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires a real Neo4j database")

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(levelname)s %(name)s: %(message)s",
        )
    )

    logging.getLogger().setLevel(logging.WARNING)
    dockb_logger = logging.getLogger("dockb")
    dockb_logger.setLevel(logging.DEBUG)
    dockb_logger.addHandler(handler)


@pytest.fixture(scope="session")
def neo4j_session():
    """Create a real Neo4j session from environment variables."""
    uri = os.environ.get("NEO4J_URL", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session(database=database) as session:
        yield session
    driver.close()
