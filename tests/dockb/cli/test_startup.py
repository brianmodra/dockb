"""Tests for the settings the shell commands resolve before starting work."""

from __future__ import annotations

import pytest

from dockb.cli import startup
from dockb.cli.startup import MissingConfigurationError, load_spacy_model, neo4j_settings


class TestNeo4jSettings:
    def test_returns_every_setting_when_all_present(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URL", "bolt://db:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "s3cret")

        assert neo4j_settings() == {
            "NEO4J_URL": "bolt://db:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "s3cret",
        }

    @pytest.mark.parametrize("absent", startup.NEO4J_VARS)
    def test_names_only_the_absent_variable(self, monkeypatch, absent):
        for name in startup.NEO4J_VARS:
            monkeypatch.setenv(name, "value")
        monkeypatch.delenv(absent)

        with pytest.raises(MissingConfigurationError) as excinfo:
            neo4j_settings()

        message = str(excinfo.value)
        assert absent in message
        for name in startup.NEO4J_VARS:
            if name != absent:
                assert name not in message

    def test_names_every_absent_variable(self, monkeypatch):
        for name in startup.NEO4J_VARS:
            monkeypatch.delenv(name, raising=False)

        with pytest.raises(MissingConfigurationError) as excinfo:
            neo4j_settings()

        message = str(excinfo.value)
        assert all(name in message for name in startup.NEO4J_VARS)

    def test_empty_value_counts_as_absent(self, monkeypatch):
        for name in startup.NEO4J_VARS:
            monkeypatch.setenv(name, "value")
        monkeypatch.setenv("NEO4J_URL", "")

        with pytest.raises(MissingConfigurationError, match="NEO4J_URL"):
            neo4j_settings()

    def test_message_points_at_dotenv(self, monkeypatch):
        for name in startup.NEO4J_VARS:
            monkeypatch.delenv(name, raising=False)

        with pytest.raises(MissingConfigurationError, match=r"\.env"):
            neo4j_settings()


class TestLoadSpacyModel:
    def test_returns_the_loaded_pipeline(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(startup.spacy, "load", lambda model: sentinel)

        assert load_spacy_model() is sentinel

    def test_loads_the_configured_model(self, monkeypatch):
        loaded: list[str] = []
        monkeypatch.setattr(startup.spacy, "load", lambda model: loaded.append(model) or object())

        load_spacy_model()

        assert loaded == [startup.SPACY_MODEL]

    def test_missing_model_raises_with_the_install_command(self, monkeypatch):
        def missing(model: str) -> object:
            raise OSError(f"[E050] Can't find model '{model}'")

        monkeypatch.setattr(startup.spacy, "load", missing)

        with pytest.raises(MissingConfigurationError) as excinfo:
            load_spacy_model()

        message = str(excinfo.value)
        assert startup.SPACY_MODEL in message
        assert f"python -m spacy download {startup.SPACY_MODEL}" in message

    def test_reraises_an_unrelated_error(self, monkeypatch):
        def broken(model: str) -> object:
            raise ValueError("the pipeline is malformed")

        monkeypatch.setattr(startup.spacy, "load", broken)

        with pytest.raises(ValueError, match="malformed"):
            load_spacy_model()
