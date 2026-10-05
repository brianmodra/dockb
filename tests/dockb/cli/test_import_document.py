"""Tests for the import_document CLI's write-back flags and default rule."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.cli import import_document as import_document_cli
from dockb.cli import startup
from dockb.cli.import_document import _default_write_back, main

_ACCOUNT_ID = "11111111-1111-1111-1111-111111111111"


class TestDefaultWriteBack:
    def test_source_inside_base_defaults_on(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        (base / "Linchpin").mkdir()

        assert _default_write_back(base / "Linchpin", str(base)) is True

    def test_source_equal_to_base_defaults_on(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()

        assert _default_write_back(base, str(base)) is True

    def test_source_outside_base_defaults_off(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        other = tmp_path / "other"
        other.mkdir()

        assert _default_write_back(other, str(base)) is False

    def test_unset_base_dir_defaults_off(self, tmp_path):
        source = tmp_path / "Linchpin"
        source.mkdir()

        assert _default_write_back(source, None) is False

    def test_comparison_is_case_sensitive_on_case_sensitive_filesystems(self, tmp_path):
        base = tmp_path / "Base"
        base.mkdir()

        assert _default_write_back(tmp_path / "BASE", str(base)) is False


class TestMainFlags:
    @staticmethod
    def _run(monkeypatch, tmp_path, *extra_args, inside_base: bool):
        base = tmp_path / "base"
        base.mkdir()
        source = base / "Linchpin" if inside_base else tmp_path / "Linchpin"
        source.mkdir()
        monkeypatch.setenv("DOCKB_CHAPTERS_DIR", str(base))
        monkeypatch.setenv("NEO4J_URL", "bolt://nowhere")
        monkeypatch.setenv("NEO4J_USER", "u")
        monkeypatch.setenv("NEO4J_PASSWORD", "p")
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            import_document_cli,
            "import_document_directory",
            lambda *args, **kwargs: captured.update(kwargs=kwargs) or [],
        )
        monkeypatch.setattr(startup.spacy, "load", lambda *a, **k: MagicMock())
        monkeypatch.setattr(import_document_cli, "SessionFactory", lambda **k: MagicMock())
        monkeypatch.setattr(import_document_cli, "account_id_for", lambda username: _ACCOUNT_ID)

        main([*extra_args, "--owner", "alice", str(source)])

        return captured, source, base

    def test_no_flag_with_external_source_passes_write_back_false(self, monkeypatch, tmp_path):
        captured, _, _ = self._run(monkeypatch, tmp_path, inside_base=False)
        assert captured["kwargs"]["write_back"] is False

    def test_no_flag_with_store_tree_source_passes_write_back_true(self, monkeypatch, tmp_path):
        captured, _, _ = self._run(monkeypatch, tmp_path, inside_base=True)
        assert captured["kwargs"]["write_back"] is True

    def test_write_back_flag_forces_on_for_external_source(self, monkeypatch, tmp_path):
        captured, _, _ = self._run(monkeypatch, tmp_path, "--write-back", inside_base=False)
        assert captured["kwargs"]["write_back"] is True

    def test_no_write_back_flag_forces_off_for_store_tree_source(self, monkeypatch, tmp_path):
        captured, _, _ = self._run(monkeypatch, tmp_path, "--no-write-back", inside_base=True)
        assert captured["kwargs"]["write_back"] is False

    def test_owner_is_forwarded_as_the_resolved_account_id(self, monkeypatch, tmp_path):
        captured, _, _ = self._run(monkeypatch, tmp_path, inside_base=False)

        assert captured["kwargs"]["owner"] == _ACCOUNT_ID

    def test_both_flags_are_rejected(self, tmp_path):
        source = tmp_path / "Linchpin"
        source.mkdir()

        with pytest.raises(SystemExit):
            main(["--write-back", "--no-write-back", str(source)])


class TestMissingStartupSettings:
    @staticmethod
    def _patch_dependencies(monkeypatch):
        monkeypatch.setattr(import_document_cli, "load_dotenv", MagicMock())
        monkeypatch.setattr(import_document_cli, "SessionFactory", MagicMock())
        monkeypatch.setattr(import_document_cli, "account_id_for", lambda username: _ACCOUNT_ID)

    def test_missing_neo4j_url_reports_and_exits_1(self, monkeypatch, capsys, tmp_path):
        for name in startup.NEO4J_VARS:
            monkeypatch.delenv(name, raising=False)
        self._patch_dependencies(monkeypatch)

        exit_code = main(["--owner", "alice", str(tmp_path)])

        assert exit_code == 1
        error = capsys.readouterr().err
        assert error.startswith("error: ")
        assert "NEO4J_URL" in error
        assert error.count("\n") == 1, "the explanation must be a single line, not a traceback"

    def test_missing_neo4j_password_names_only_that_variable(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv("NEO4J_URL", "bolt://nowhere")
        monkeypatch.setenv("NEO4J_USER", "u")
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        self._patch_dependencies(monkeypatch)

        exit_code = main(["--owner", "alice", str(tmp_path)])

        assert exit_code == 1
        error = capsys.readouterr().err
        assert "NEO4J_PASSWORD" in error
        assert "NEO4J_URL" not in error

    def test_empty_neo4j_url_counts_as_missing(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv("NEO4J_URL", "")
        monkeypatch.setenv("NEO4J_USER", "u")
        monkeypatch.setenv("NEO4J_PASSWORD", "p")
        self._patch_dependencies(monkeypatch)

        exit_code = main(["--owner", "alice", str(tmp_path)])

        assert exit_code == 1
        assert "NEO4J_URL" in capsys.readouterr().err

    def test_missing_neo4j_settings_do_not_load_the_spacy_model(self, monkeypatch, tmp_path):
        for name in startup.NEO4J_VARS:
            monkeypatch.delenv(name, raising=False)
        self._patch_dependencies(monkeypatch)
        loaded: list[str] = []
        monkeypatch.setattr(startup.spacy, "load", lambda model: loaded.append(model) or MagicMock())

        main(["--owner", "alice", str(tmp_path)])

        assert not loaded

    def test_missing_spacy_model_reports_and_exits_1(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv("NEO4J_URL", "bolt://nowhere")
        monkeypatch.setenv("NEO4J_USER", "u")
        monkeypatch.setenv("NEO4J_PASSWORD", "p")
        self._patch_dependencies(monkeypatch)

        def missing_model(model: str) -> object:
            raise OSError(f"[E050] Can't find model '{model}'")

        monkeypatch.setattr(startup.spacy, "load", missing_model)
        session_factory = MagicMock()
        monkeypatch.setattr(import_document_cli, "SessionFactory", lambda **k: session_factory)

        exit_code = main(["--owner", "alice", str(tmp_path)])

        assert exit_code == 1
        error = capsys.readouterr().err
        assert startup.SPACY_MODEL in error
        assert f"python -m spacy download {startup.SPACY_MODEL}" in error
        session_factory.session.assert_not_called()

    def test_unrelated_spacy_error_still_propagates(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NEO4J_URL", "bolt://nowhere")
        monkeypatch.setenv("NEO4J_USER", "u")
        monkeypatch.setenv("NEO4J_PASSWORD", "p")
        self._patch_dependencies(monkeypatch)

        def broken(model: str) -> object:
            raise ValueError("the pipeline is malformed")

        monkeypatch.setattr(startup.spacy, "load", broken)

        with pytest.raises(ValueError, match="malformed"):
            main(["--owner", "alice", str(tmp_path)])


class TestDocumentOwner:
    """The imported document is stored under the named account, never under nobody's."""

    @staticmethod
    def _patch_dependencies(monkeypatch):
        monkeypatch.setattr(import_document_cli, "load_dotenv", MagicMock())
        monkeypatch.setattr(import_document_cli, "SessionFactory", MagicMock())
        monkeypatch.setattr(startup.spacy, "load", lambda *a, **k: MagicMock())
        monkeypatch.setenv("NEO4J_URL", "bolt://nowhere")
        monkeypatch.setenv("NEO4J_USER", "u")
        monkeypatch.setenv("NEO4J_PASSWORD", "p")

    def test_owner_is_required(self, monkeypatch, capsys, tmp_path):
        self._patch_dependencies(monkeypatch)
        monkeypatch.setattr(import_document_cli, "import_document_directory", MagicMock())

        exit_code = main([str(tmp_path)])

        assert exit_code == 1
        error = capsys.readouterr().err
        assert "--owner is required" in error
        assert error.count("\n") == 1, "the explanation must be a single line, not a traceback"

    def test_unknown_owner_reports_and_exits_1(self, monkeypatch, capsys, tmp_path):
        self._patch_dependencies(monkeypatch)

        def unknown(username: str) -> str:
            raise startup.UnknownUserError(f"unknown user {username!r}")

        monkeypatch.setattr(import_document_cli, "account_id_for", unknown)

        exit_code = main(["--owner", "nobody", str(tmp_path)])

        assert exit_code == 1
        assert "unknown user 'nobody'" in capsys.readouterr().err
