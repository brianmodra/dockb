"""Tests for the ``python -m dockb.cli.reconstruct_chapter`` CLI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.cli import reconstruct_chapter as cli
from dockb.cli import startup
from dockb.exceptions import ChapterMismatchError
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository

_ACCOUNT_ID = "11111111-1111-1111-1111-111111111111"


class TestReconstructChapter:
    @pytest.fixture
    def _neo4j_env(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URL", "bolt://test:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    def _patch_dependencies(self, monkeypatch):
        monkeypatch.setattr(cli, "load_dotenv", MagicMock())
        session_factory = MagicMock()
        session_cm = MagicMock()
        session = MagicMock()
        session_cm.__enter__.return_value = session
        session_factory.session.return_value = session_cm
        session_factory_maker = MagicMock(return_value=session_factory)
        monkeypatch.setattr(cli, "SessionFactory", session_factory_maker)
        self.nlp = MagicMock()
        monkeypatch.setattr(startup.spacy, "load", lambda *a, **k: self.nlp)
        self.session_factory_maker = session_factory_maker
        monkeypatch.setattr(cli, "account_id_for", lambda username: _ACCOUNT_ID)

    def test_without_out_writes_into_store_layout(self, _neo4j_env, capsys, monkeypatch, tmp_path):
        self._patch_dependencies(monkeypatch)
        captured = []

        def fake_store_reconstruct(cid, repo, doc_repo, store, nlp):
            captured.append((cid, repo, doc_repo, store, nlp))
            return store.chapter_file("Faith", "Act I", "Intro")

        monkeypatch.setattr(cli, "reconstruct_chapter_to_store", fake_store_reconstruct)
        monkeypatch.setattr(cli, "resolve_document_base_dir", lambda *a, **k: tmp_path)

        exit_code = cli.main(["c1", "--owner", "alice"])

        assert exit_code == 0
        assert capsys.readouterr().out == str(tmp_path / _ACCOUNT_ID / "Faith" / "Act I" / "Intro.md") + "\n"
        chapter_id, chapter_repo, document_repo, store, nlp = captured[0]
        assert chapter_id == "c1"
        assert isinstance(chapter_repo, ChapterRepository)
        assert isinstance(document_repo, DocumentRepository)
        assert isinstance(store, cli.DocumentStore)
        assert store.account_id == _ACCOUNT_ID
        assert nlp is self.nlp
        self.session_factory_maker.return_value.session.assert_called_once_with()
        self.session_factory_maker.return_value.close.assert_called_once_with()

    def test_requires_an_owner_when_writing_to_the_store(self, _neo4j_env, capsys, monkeypatch):
        """Without an account there is no directory to write into.

        Falling back to a shared tree would put two accounts' chapters under one
        title, so the command refuses rather than guessing.
        """
        self._patch_dependencies(monkeypatch)

        exit_code = cli.main(["c1"])

        assert exit_code == 1
        assert "--owner is required" in capsys.readouterr().err

    def test_writes_to_file_with_out(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch)
        captured = []
        monkeypatch.setattr(cli, "reconstruct_chapter_file", lambda cid, repo, path, nlp: captured.append((cid, repo, path, nlp)) or None)

        exit_code = cli.main(["c1", "--out", "out.md"])

        assert exit_code == 0
        chapter_id, chapter_repo, path, nlp = captured[0]
        assert chapter_id == "c1"
        assert isinstance(chapter_repo, ChapterRepository)
        assert str(path) == "out.md"
        assert nlp is self.nlp

    def test_missing_chapter_id_exits_with_usage(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch)

        with pytest.raises(SystemExit) as excinfo:
            cli.main([])

        assert excinfo.value.code == 2

    def test_unknown_chapter_prints_error_and_exits_1(self, _neo4j_env, capsys, monkeypatch, tmp_path):
        self._patch_dependencies(monkeypatch)
        monkeypatch.setattr(cli, "resolve_document_base_dir", lambda *a, **k: tmp_path)

        def raise_missing(*args):
            raise ChapterMismatchError("Chapter 'nope' was not found in the knowledge graph")

        monkeypatch.setattr(cli, "reconstruct_chapter_to_store", raise_missing)

        exit_code = cli.main(["nope", "--owner", "alice"])

        assert exit_code == 1
        assert "not found in the knowledge graph" in capsys.readouterr().err

    def test_missing_neo4j_url_reports_and_exits_1(self, monkeypatch, capsys):
        monkeypatch.delenv("NEO4J_URL", raising=False)
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        self._patch_dependencies(monkeypatch)

        exit_code = cli.main(["c1", "--owner", "alice"])

        assert exit_code == 1
        error = capsys.readouterr().err
        assert error.startswith("error: ")
        assert "NEO4J_URL" in error
        assert error.count("\n") == 1, "the explanation must be a single line, not a traceback"
        self.session_factory_maker.assert_not_called()

    def test_empty_neo4j_url_reports_and_exits_1(self, monkeypatch, capsys):
        monkeypatch.setenv("NEO4J_URL", "")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        self._patch_dependencies(monkeypatch)

        exit_code = cli.main(["c1", "--owner", "alice"])

        assert exit_code == 1
        assert "NEO4J_URL" in capsys.readouterr().err

    def test_missing_spacy_model_reports_and_exits_1(self, _neo4j_env, monkeypatch, capsys):
        self._patch_dependencies(monkeypatch)

        def missing_model(model: str) -> object:
            raise OSError(f"[E050] Can't find model '{model}'")

        monkeypatch.setattr(startup.spacy, "load", missing_model)

        exit_code = cli.main(["c1", "--owner", "alice"])

        assert exit_code == 1
        error = capsys.readouterr().err
        assert startup.SPACY_MODEL in error
        assert f"python -m spacy download {startup.SPACY_MODEL}" in error
        self.session_factory_maker.assert_not_called()
