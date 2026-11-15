"""Tests for the ``dockb migrate-layout`` CLI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.cli import migrate_layout as cli


class TestMigrateLayout:
    @pytest.fixture
    def _neo4j_env(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URL", "bolt://test:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    def _patch_dependencies(self, monkeypatch, records):
        monkeypatch.setattr(cli, "load_dotenv", MagicMock())
        session = MagicMock()
        session.run.return_value = records
        session_cm = MagicMock()
        session_cm.__enter__.return_value = session
        factory = MagicMock()
        factory.session.return_value = session_cm
        factory_maker = MagicMock(return_value=factory)
        monkeypatch.setattr(cli, "SessionFactory", factory_maker)
        return session, factory, factory_maker

    def test_migrates_every_old_quote_type_into_a_layout(self, _neo4j_env, capsys, monkeypatch):
        records = [
            {"paragraph_id": "p-normal", "quote_type": ""},
            {"paragraph_id": "p-read", "quote_type": "reading"},
            {"paragraph_id": "p-write", "quote_type": "writing"},
        ]
        session, factory, _factory_maker = self._patch_dependencies(monkeypatch, records)

        assert cli.main([]) == 0

        assert capsys.readouterr().out == "migrated 3 paragraph(s)\n"
        select_call, update_call = session.run.call_args_list
        assert select_call.args[1] == {"document_id": None}
        assert update_call.args[1] == {
            "rows": [
                {"paragraph_id": "p-normal", "layout_kind": "normal", "layout_variant": ""},
                {"paragraph_id": "p-read", "layout_kind": "quoted", "layout_variant": "reading"},
                {"paragraph_id": "p-write", "layout_kind": "quoted", "layout_variant": "writing"},
            ]
        }
        assert "REMOVE p.quote_type" in update_call.args[0]
        factory.close.assert_called_once_with()

    def test_dry_run_reports_without_writing(self, _neo4j_env, capsys, monkeypatch):
        session, _factory, _factory_maker = self._patch_dependencies(monkeypatch, [{"paragraph_id": "p-read", "quote_type": "reading"}])

        assert cli.main(["--dry-run"]) == 0

        assert capsys.readouterr().out == "would migrate 1 paragraph(s)\n"
        assert session.run.call_count == 1

    def test_document_id_limits_the_scan(self, _neo4j_env, monkeypatch):
        session, _factory, _factory_maker = self._patch_dependencies(monkeypatch, [])

        assert cli.main(["--document-id", "doc-1"]) == 0

        assert session.run.call_args.args[1] == {"document_id": "doc-1"}

    def test_nothing_to_do_is_success(self, _neo4j_env, capsys, monkeypatch):
        session, _factory, _factory_maker = self._patch_dependencies(monkeypatch, [])

        assert cli.main([]) == 0

        assert capsys.readouterr().out == "migrated 0 paragraph(s)\n"
        assert session.run.call_count == 1
        assert "p.quote_type IS NOT NULL" in session.run.call_args.args[0]

    def test_unknown_quote_type_refuses_the_whole_run(self, _neo4j_env, capsys, monkeypatch):
        session, factory, _factory_maker = self._patch_dependencies(monkeypatch, [{"paragraph_id": "p-odd", "quote_type": "aside"}])

        assert cli.main([]) == 1

        error = capsys.readouterr().err
        assert error == "error: paragraph 'p-odd' has quote_type 'aside'; expected '', 'reading', or 'writing'\n"
        assert session.run.call_count == 1
        factory.close.assert_called_once_with()

    def test_missing_neo4j_settings_report_one_line_without_opening_a_session(self, capsys, monkeypatch):
        monkeypatch.setattr(cli, "load_dotenv", MagicMock())
        monkeypatch.delenv("NEO4J_URL", raising=False)
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        factory_maker = MagicMock()
        monkeypatch.setattr(cli, "SessionFactory", factory_maker)

        assert cli.main([]) == 1

        error = capsys.readouterr().err
        assert error.startswith("error: ")
        assert "NEO4J_URL" in error
        assert error.count("\n") == 1
        factory_maker.assert_not_called()

    def test_malformed_arguments_exit_with_usage(self, _neo4j_env, monkeypatch):
        self._patch_dependencies(monkeypatch, [])

        with pytest.raises(SystemExit) as excinfo:
            cli.main(["--unknown"])

        assert excinfo.value.code == 2
