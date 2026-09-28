"""Settings the shell commands need before they can do any work.

Both ``import_document`` and ``reconstruct_chapter`` read the same Neo4j
connection settings and load the same spaCy pipeline. Resolving them here keeps
one spelling of each variable and one message per failure, so a shell command
reports a missing setting instead of a traceback.
"""

from __future__ import annotations

import os

import spacy
from spacy.language import Language

NEO4J_VARS = ("NEO4J_URL", "NEO4J_USER", "NEO4J_PASSWORD")

SPACY_MODEL = "en_core_web_sm"


class MissingConfigurationError(Exception):
    """A required setting is absent, so the command cannot start."""


def neo4j_settings() -> dict[str, str]:
    """Return the Neo4j connection settings, naming every absent one on failure.

    A variable set to the empty string counts as absent: it cannot reach a
    database, so it is as missing as one that was never exported.
    """
    values = {name: os.environ.get(name, "") for name in NEO4J_VARS}
    missing = [name for name in NEO4J_VARS if not values[name]]
    if missing:
        raise MissingConfigurationError(f"{', '.join(missing)} must be set in the environment or a .env file")
    return values


def load_spacy_model() -> Language:
    """Return the loaded sentence pipeline, or raise on a missing model.

    Only a model that cannot be found is translated: a pipeline that is present
    but broken is a real fault and keeps its own traceback rather than being
    reported as a missing setting.
    """
    try:
        return spacy.load(SPACY_MODEL)
    except OSError as exc:
        raise MissingConfigurationError(
            f"the spaCy model '{SPACY_MODEL}' is not installed — install it with: python -m spacy download {SPACY_MODEL}"
        ) from exc
