"""Tests for the per-account intent journal (WAL) and its factory wiring."""

from __future__ import annotations

import os

import pytest

from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.infrastructure.document_store.journal import JOURNAL_DIRNAME, Journal, JournalRecord
from dockb.infrastructure.document_store.store import DocumentStore


def _record(op_id: str = "op-1") -> JournalRecord:
    return JournalRecord(
        op="document-rename",
        op_id=op_id,
        account_id="acct-1",
        document_id="doc-1",
        payload={"from": "Linchpin", "to": "Wheels"},
    )


@pytest.fixture()
def journal(tmp_path):
    return Journal(tmp_path / JOURNAL_DIRNAME)


class TestJournalRecord:  # pylint: disable=too-few-public-methods
    def test_new_mints_a_unique_op_id(self):
        first = JournalRecord.new("document-rename", "acct-1", "doc-1", {"from": "A", "to": "B"})
        second = JournalRecord.new("document-rename", "acct-1", "doc-1", {"from": "A", "to": "B"})

        assert first.op == "document-rename"
        assert first.payload == {"from": "A", "to": "B"}
        assert first.op_id and second.op_id
        assert first.op_id != second.op_id


class TestJournalWrite:
    def test_write_then_pending_round_trips(self, journal):
        record = _record()
        journal.write(record)

        assert journal.pending() == [record]

    def test_write_names_the_file_after_the_op_id(self, journal):
        record = _record(op_id="abc123")
        path = journal.write(record)

        assert path == journal.directory / "abc123.yaml"
        assert path.is_file()

    def test_write_creates_the_directory(self, journal):
        assert not journal.directory.exists()
        journal.write(_record())
        assert journal.directory.is_dir()

    def test_write_leaves_no_temp_file_behind(self, journal):
        journal.write(_record())
        names = sorted(p.name for p in journal.directory.iterdir())
        assert names == ["op-1.yaml"]

    def test_write_overwrites_the_same_op_id(self, journal):
        journal.write(_record())
        journal.write(_record())
        assert len(journal.pending()) == 1

    def test_write_rejects_an_unsafe_op_id(self, journal):
        with pytest.raises(ValueError):
            journal.write(_record(op_id="../../escape"))

    def test_failed_replace_leaves_the_previous_record_intact(self, journal, monkeypatch):
        journal.write(_record())

        def boom(*_args, **_kwargs):
            raise OSError("replace failed")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            journal.write(_record(op_id="op-1"))
        monkeypatch.undo()

        assert journal.pending() == [_record()]
        assert sorted(p.name for p in journal.directory.iterdir()) == ["op-1.yaml"]


class TestJournalPending:
    def test_pending_is_empty_without_a_directory(self, journal):
        assert journal.pending() == []

    def test_pending_is_sorted_by_op_id(self, journal):
        journal.write(_record("op-b"))
        journal.write(_record("op-a"))
        assert [r.op_id for r in journal.pending()] == ["op-a", "op-b"]

    def test_pending_quarantines_a_malformed_record(self, journal):
        journal.directory.mkdir(parents=True)
        bad = journal.directory / "op-bad.yaml"
        bad.write_text("op: [unclosed\n", encoding="utf-8")

        assert journal.pending() == []
        assert not bad.exists()
        assert (journal.directory / "quarantine" / "op-bad.yaml").is_file()

    def test_pending_quarantines_a_record_missing_required_fields(self, journal):
        journal.directory.mkdir(parents=True)
        bad = journal.directory / "op-partial.yaml"
        bad.write_text("op: document-rename\n", encoding="utf-8")

        assert journal.pending() == []
        assert (journal.directory / "quarantine" / "op-partial.yaml").is_file()

    def test_pending_quarantines_a_record_whose_op_id_does_not_match_its_filename(self, journal):
        journal.directory.mkdir(parents=True)
        bad = journal.directory / "op-1.yaml"
        bad.write_text(
            "op: document-rename\nop_id: ../../../etc/passwd\naccount_id: acct-1\ndocument_id: doc-1\n",
            encoding="utf-8",
        )

        assert journal.pending() == []
        assert (journal.directory / "quarantine" / "op-1.yaml").is_file()

    def test_pending_keeps_the_good_records_when_one_is_malformed(self, journal):
        journal.write(_record("op-good"))
        journal.directory.joinpath("op-bad.yaml").write_text("::not yaml::", encoding="utf-8")

        assert [r.op_id for r in journal.pending()] == ["op-good"]

    def test_pending_ignores_the_quarantine_directory(self, journal):
        journal.directory.mkdir(parents=True)
        quarantined = journal.directory / "quarantine"
        quarantined.mkdir()
        (quarantined / "op-old.yaml").write_text("::still not yaml::", encoding="utf-8")

        assert journal.pending() == []


class TestJournalRemoveAndQuarantine:
    def test_remove_deletes_the_record(self, journal):
        journal.write(_record())
        journal.remove("op-1")
        assert journal.pending() == []

    def test_remove_is_a_noop_when_absent(self, journal):
        journal.remove("missing")
        assert journal.pending() == []

    def test_remove_rejects_an_unsafe_op_id(self, journal):
        with pytest.raises(ValueError):
            journal.remove("../../escape")

    def test_quarantine_moves_the_named_record(self, journal):
        journal.write(_record())
        destination = journal.quarantine("op-1")

        assert destination == journal.directory / "quarantine" / "op-1.yaml"
        assert destination.is_file()
        assert not (journal.directory / "op-1.yaml").exists()


class TestFactoryJournals:
    def test_journal_for_returns_the_account_journal(self, tmp_path):
        factory = DocumentStoreFactory(base_dir=tmp_path)
        journal = factory.journal_for("acct-1")

        assert journal.directory == tmp_path / "acct-1" / JOURNAL_DIRNAME

    def test_journal_accounts_lists_only_accounts_with_a_journal(self, tmp_path):
        (tmp_path / "acct-1" / JOURNAL_DIRNAME).mkdir(parents=True)
        (tmp_path / "acct-2").mkdir()
        (tmp_path / "acct-3" / JOURNAL_DIRNAME).mkdir(parents=True)

        assert DocumentStoreFactory(base_dir=tmp_path).journal_accounts() == ["acct-1", "acct-3"]

    def test_journal_accounts_is_empty_when_the_base_is_missing(self, tmp_path):
        assert DocumentStoreFactory(base_dir=tmp_path / "absent").journal_accounts() == []


class TestStoreJournal:  # pylint: disable=too-few-public-methods
    def test_store_journal_lives_outside_any_document_directory(self, tmp_path):
        store = DocumentStore(base_dir=tmp_path, account_id="acct-1")

        journal = store.journal()

        assert journal.directory == tmp_path / "acct-1" / JOURNAL_DIRNAME
        assert store.document_dir("Linchpin") not in journal.directory.parents
