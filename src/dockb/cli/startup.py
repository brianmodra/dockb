"""Settings the shell commands need before they can do any work.

``import_document`` and ``reconstruct_chapter`` read the same Neo4j connection
settings, load the same spaCy pipeline, and name their account by the same
username. Resolving them here keeps one spelling of each variable and one message
per failure, so a shell command reports a missing setting instead of a traceback.
"""

from __future__ import annotations

import os

import spacy
from dotenv import load_dotenv
from spacy.language import Language

from dockb.composition import resolve_document_base_dir
from dockb.infrastructure.accounts.store import AccountStore, normalize_username

NEO4J_VARS = ("NEO4J_URL", "NEO4J_USER", "NEO4J_PASSWORD")

SPACY_MODEL = "en_core_web_sm"


class MissingConfigurationError(Exception):
    """A required setting is absent, so the command cannot start."""


class UnknownUserError(Exception):
    """No account exists for the username a command named."""


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


def account_id_for(username: str) -> str:
    """Return the account id for *username*, the internal id documents are owned by.

    The markdown tree is keyed by account id rather than username, so a command
    naming a user resolves the id here instead of building a path from the name a
    human typed. Usernames stay mutable provider data; the id does not move when one
    changes. Raises :class:`MissingConfigurationError` when the account database is
    not configured or readable, and :class:`UnknownUserError` when there is no such
    user.
    """
    load_dotenv()
    secret = os.environ.get("DOCKB_SECRET_KEY", "")
    if not secret.strip():
        raise MissingConfigurationError("DOCKB_SECRET_KEY must be set in the environment or a .env file")
    row = AccountStore(base_dir=resolve_document_base_dir(), secret=secret).get_user(normalize_username(username))
    if row is None:
        raise UnknownUserError(f"unknown user {normalize_username(username)!r}")
    return str(row["id"])
