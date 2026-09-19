"""Tests for the ``python -m dockb.cli.reconstruct_chapter`` CLI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.cli import reconstruct_chapter as cli
from dockb.exceptions import ChapterMismatchError
from dockb.repositories.chapter_repository import ChapterRepository


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
        monkeypatch.setattr(cli.spacy, "load", lambda *a, **k: self.nlp)
        self.session_factory_maker = session_factory_maker

    def test_prints_rendered_chapter_to_stdout(self, _neo4j_env, capsys, monkeypatch):
        self._patch_dependencies(monkeypatch)
        captured = []
        monkeypatch.setattr(cli, "reconstruct_chapter_markdown", lambda cid, repo, nlp: captured.append((cid, repo, nlp)) or "# ch\n")

        exit_code = cli.main(["c1"])

        assert exit_code == 0
        assert capsys.readouterr().out == "# ch\n"
        chapter_id, chapter_repo, nlp = captured[0]
        assert chapter_id == "c1"
        assert isinstance(chapter_repo, ChapterRepository)
        assert nlp is self.nlp
        self.session_factory_maker.return_value.session.assert_called_once_with()
        self.session_factory_maker.return_value.close.assert_called_once_with()

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

    def test_unknown_chapter_prints_error_and_exits_1(self, _neo4j_env, capsys, monkeypatch):
        self._patch_dependencies(monkeypatch)

        def raise_missing(cid, repo, nlp):
            raise ChapterMismatchError("Chapter 'nope' was not found in the knowledge graph")

        monkeypatch.setattr(cli, "reconstruct_chapter_markdown", raise_missing)

        exit_code = cli.main(["nope"])

        assert exit_code == 1
        assert "not found in the knowledge graph" in capsys.readouterr().err

    def test_missing_neo4j_url_is_an_error(self, monkeypatch):
        monkeypatch.delenv("NEO4J_URL", raising=False)
        self._patch_dependencies(monkeypatch)

        with pytest.raises(KeyError, match="NEO4J_URL"):
            cli.main(["c1"])
