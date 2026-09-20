"""Tests for the ``python -m dockb.cli.import_document`` CLI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dockb.cli import import_document as cli
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.markdown_import import ChapterImportSummary


class TestImportDocument:
    @pytest.fixture
    def _neo4j_env(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URL", "bolt://test:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    def _patch_dependencies(self, monkeypatch):
        monkeypatch.setattr(cli, "load_dotenv", MagicMock())
        self.session_factory = MagicMock()
        session_cm = MagicMock()
        self.session = MagicMock()
        session_cm.__enter__.return_value = self.session
        self.session_factory.session.return_value = session_cm
        self.session_factory_maker = MagicMock(return_value=self.session_factory)
        monkeypatch.setattr(cli, "SessionFactory", self.session_factory_maker)
        self.nlp = MagicMock()
        monkeypatch.setattr(cli.spacy, "load", lambda *a, **k: self.nlp)
        monkeypatch.setattr(cli, "getpass", SimpleNamespace(getuser=lambda: "bob"))

    def test_imports_directory_and_prints_a_line_per_summary(self, _neo4j_env, capsys, monkeypatch):
        self._patch_dependencies(monkeypatch)
        summaries = [
            ChapterImportSummary(chapter_id="c1", created=True, title="Ch 1"),
            ChapterImportSummary(chapter_id="c2", created=False, title="Ch 2"),
        ]
        captured = []
        monkeypatch.setattr(cli, "import_document_directory", lambda *args: captured.append(args) or summaries)

        exit_code = cli.main(["docs/Linchpin"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "c1 imported: Ch 1" in out
        assert "c2 synced: Ch 2" in out
        document_dir, user, nlp, document_repo, chapter_repo, uow_factory, single_newline = captured[0]
        assert document_dir == Path("docs/Linchpin")
        assert user == "bob"
        assert nlp is self.nlp
        assert isinstance(document_repo, DocumentRepository)
        assert isinstance(chapter_repo, ChapterRepository)
        assert isinstance(uow_factory, UnitOfWorkFactory)
        assert single_newline is False
        self.session_factory.session.assert_called_once_with()
        self.session_factory.close.assert_called_once_with()

    def test_single_newline_paragraphs_flag_is_forwarded(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch)
        captured = []
        monkeypatch.setattr(cli, "import_document_directory", lambda *args: captured.append(args) or [])

        exit_code = cli.main(["docs/Linchpin", "--single-newline-paragraphs"])

        assert exit_code == 0
        assert captured[0][6] is True

    def test_reads_neo4j_configuration_from_environment(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch)
        monkeypatch.setattr(cli, "import_document_directory", lambda *args: [])

        cli.main(["docs/Linchpin"])

        self.session_factory_maker.assert_called_once_with(
            uri="bolt://test:7687",
            user="neo4j",
            password="secret",
        )

    def test_missing_directory_argument_exits_with_usage(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch)

        with pytest.raises(SystemExit) as excinfo:
            cli.main([])

        assert excinfo.value.code == 2

    def test_registers_repositories_for_every_persisted_model_type(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch)
        captured = []
        monkeypatch.setattr(
            cli,
            "UnitOfWorkFactory",
            lambda **kwargs: captured.append(kwargs) or MagicMock(),
        )
        monkeypatch.setattr(cli, "import_document_directory", lambda *args: [])
        from dockb.models.chapter import Chapter
        from dockb.models.document import Document
        from dockb.models.paragraph import Paragraph
        from dockb.models.sentence import Sentence

        cli.main(["docs/Linchpin"])

        repos = captured[0]["repos"]
        for model_type in (Document, Chapter, Paragraph, Sentence):
            assert model_type in repos, f"no repository registered for {model_type.__name__}"

    def test_missing_neo4j_url_is_an_error(self, monkeypatch):
        monkeypatch.delenv("NEO4J_URL", raising=False)
        self._patch_dependencies(monkeypatch)

        with pytest.raises(KeyError, match="NEO4J_URL"):
            cli.main(["docs/Linchpin"])
