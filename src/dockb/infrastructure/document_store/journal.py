"""A durable per-account intent journal for operations that write two stores.

Some operations write both Neo4j and the markdown tree, and the two cannot share
one commit: a crash between them leaves the stores disagreeing, and the filesystem
half (``git mv`` + ``git commit``) cannot be rolled back. The journal is a
write-ahead record of the operation's *desired end state* — appended before the
first mutation and removed once every store agrees — so a later drain can re-apply
it. Because a record names the end state rather than a step plan, replay is
idempotent.

One record is one small YAML file named ``<op_id>.yaml`` in a per-account
``.dockb-journal`` directory that sits outside any document directory a rename
could move. A record that cannot be read is quarantined rather than dropped.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dockb.titles import validate_segment

JOURNAL_DIRNAME = ".dockb-journal"
_QUARANTINE_DIRNAME = "quarantine"
_RECORD_SUFFIX = ".yaml"


class MalformedRecordError(ValueError):
    """A journal file that cannot be read as a record."""


@dataclass(frozen=True)
class JournalRecord:
    """One pending operation's desired end state, durable until it is removed."""

    op: str
    op_id: str
    account_id: str
    document_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, op: str, account_id: str, document_id: str, payload: dict[str, Any] | None = None) -> JournalRecord:
        """Build a record with a freshly minted, unique ``op_id``."""
        return cls(op=op, op_id=uuid.uuid4().hex, account_id=account_id, document_id=document_id, payload=payload or {})

    def to_dict(self) -> dict[str, Any]:
        """Return the mapping written to disk for this record."""
        return {
            "op": self.op,
            "op_id": self.op_id,
            "account_id": self.account_id,
            "document_id": self.document_id,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Any) -> JournalRecord:
        """Build a record from a parsed mapping, raising on anything malformed."""
        if not isinstance(data, dict):
            raise MalformedRecordError("record is not a mapping")
        try:
            op = str(data["op"])
            op_id = str(data["op_id"])
            account_id = str(data["account_id"])
            document_id = str(data["document_id"])
        except KeyError as exc:
            raise MalformedRecordError(f"record is missing field {exc}") from exc
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            raise MalformedRecordError("record payload is not a mapping")
        return cls(
            op=op,
            op_id=op_id,
            account_id=account_id,
            document_id=document_id,
            payload={str(key): value for key, value in payload.items()},
        )


class Journal:
    """Read and write one directory's worth of pending-operation records."""

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)

    @property
    def directory(self) -> Path:
        """The directory holding this journal's records."""
        return self._directory

    def write(self, record: JournalRecord) -> Path:
        """Durably write *record* to ``<op_id>.yaml``; return the file written.

        The record lands via a temp file in the same directory, flushed and fsynced,
        then ``os.replace``d into place and the directory fsynced — so a crash leaves
        either the old record or the new one, never a torn file. A failed replace
        removes the temp file and leaves any previous record intact.
        """
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._record_path(record.op_id)
        temp = self._directory / f".{record.op_id}{_RECORD_SUFFIX}.tmp"
        text = yaml.safe_dump(record.to_dict(), default_flow_style=False, allow_unicode=True, sort_keys=False)
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            self._fsync_directory()
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return path

    def pending(self) -> list[JournalRecord]:
        """Return the readable records, sorted by ``op_id``.

        A file that cannot be read as a record is moved to ``quarantine/`` as it is
        encountered, so a malformed record is never silently dropped and never blocks
        the records around it.
        """
        if not self._directory.is_dir():
            return []
        records: list[JournalRecord] = []
        for path in sorted(self._directory.glob(f"*{_RECORD_SUFFIX}")):
            try:
                records.append(self._read(path))
            except MalformedRecordError:
                self.quarantine(path.stem)
        return records

    def remove(self, op_id: str) -> None:
        """Delete the record named *op_id*; absent is a no-op."""
        self._record_path(op_id).unlink(missing_ok=True)

    def quarantine(self, op_id: str) -> Path:
        """Move the record named *op_id* under ``quarantine/``; return its new path."""
        source = self._record_path(op_id)
        destination_dir = self._directory / _QUARANTINE_DIRNAME
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        os.replace(source, destination)
        return destination

    def _read(self, path: Path) -> JournalRecord:
        """Parse *path* into a record, raising MalformedRecordError on any problem.

        The record's ``op_id`` must equal its filename: the drain removes a record by
        the ``op_id`` it read, so a file whose content names a different id — or a
        path outside the journal — is malformed, not something to act on.
        """
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise MalformedRecordError(f"cannot read {path.name}: {exc}") from exc
        record = JournalRecord.from_dict(data)
        if record.op_id != path.stem:
            raise MalformedRecordError(f"{path.name} names op_id {record.op_id!r}")
        return record

    def _record_path(self, op_id: str) -> Path:
        """Resolve ``<op_id>.yaml`` inside the journal, refusing an id that is not a segment."""
        validate_segment(op_id)
        return self._directory / f"{op_id}{_RECORD_SUFFIX}"

    def _fsync_directory(self) -> None:
        """Flush the directory entry so a rename survives a crash.

        Best-effort: some platforms cannot open a directory for reading, and the
        file's own contents were already fsynced before the replace.
        """
        try:
            handle = os.open(self._directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
