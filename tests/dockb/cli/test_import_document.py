"""Tests for the import_document CLI's write-back flags and default rule."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.cli import import_document as import_document_cli
from dockb.cli.import_document import _default_write_back, main


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
        monkeypatch.setattr(import_document_cli.spacy, "load", lambda *a, **k: MagicMock())
        monkeypatch.setattr(import_document_cli, "SessionFactory", lambda **k: MagicMock())

        main([*extra_args, str(source)])

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

    def test_both_flags_are_rejected(self, tmp_path):
        source = tmp_path / "Linchpin"
        source.mkdir()

        with pytest.raises(SystemExit):
            main(["--write-back", "--no-write-back", str(source)])
