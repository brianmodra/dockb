"""Tests for ImportService — staging an upload and importing it."""

# pylint: disable=unused-argument,too-few-public-methods,protected-access

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dockb.exceptions import DocumentFormatError, DocumentOwnershipError
from dockb.services import import_service as import_service_module
from dockb.services.import_service import ImportService
from dockb.services.markdown_import import ChapterImportSummary
from dockb.uploads import MAX_FILE_COUNT, MAX_TOTAL_BYTES, UploadRejectedError, UploadTooLargeError

_OWNER = "acct-1"
_USERNAME = "abby"


class FakeUpload:
    """A multipart part with the fields ImportService uses."""

    def __init__(self, filename: str | None, content: bytes = b"body") -> None:
        self.filename = filename
        self._content = content
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk, self._offset = self._content[self._offset :], len(self._content)
            return chunk
        chunk = self._content[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class RecordingWalker:
    """Stands in for the directory walker, recording the tree it was handed."""

    def __init__(self, tree: dict[str, bytes] | None = None, raises: Exception | None = None) -> None:
        self.tree = tree if tree is not None else {}
        self.raises = raises
        self.calls: list[dict[str, object]] = []

    def __call__(self, document_dir, user_name, nlp, document_repo, chapter_repo, uow_factory, **kwargs):
        base = Path(document_dir)
        self.calls.append({"path": Path(document_dir), "user_name": user_name, **kwargs})
        for name in self.tree:
            assert (base / name).is_file(), f"{name} was not staged"
        if self.raises is not None:
            raise self.raises
        return [ChapterImportSummary(chapter_id="c1", created=True, title="Opening 1")]


@pytest.fixture()
def service():
    return ImportService(nlp=None, document_repo=None, chapter_repo=None, uow_factory=None)


@pytest.fixture()
def walker(monkeypatch):
    recorder = RecordingWalker()
    monkeypatch.setattr(import_service_module, "import_document_directory", recorder)
    return recorder


class TestImportParts:
    @pytest.mark.asyncio
    async def test_stages_files_and_imports_them(self, service, walker, tmp_path):
        walker.tree = {"Act I/Opening 1.md": b"one", "document_metadata.yaml": b"title: X"}
        parts = [FakeUpload("Linchpin/Act I/Opening 1.md", b"one"), FakeUpload("Linchpin/document_metadata.yaml", b"title: X")]

        result = await service.import_parts(parts, "abby", owner=_OWNER)

        assert [s.chapter_id for s in result] == ["c1"]
        assert walker.calls[0]["path"].name == "Linchpin"

    @pytest.mark.asyncio
    async def test_uses_the_shared_root_as_the_document_directory(self, service, monkeypatch):
        """The upload's document folder is the directory handed to the walker."""
        seen: list[str] = []

        def capture(document_dir, *_args, **_kwargs):
            seen.append(Path(document_dir).name)
            return []

        monkeypatch.setattr(import_service_module, "import_document_directory", capture)
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)
        assert seen == ["Linchpin"]

    @pytest.mark.asyncio
    async def test_never_writes_back_the_uploaded_bytes(self, service, walker):
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)
        assert walker.calls[0]["write_back"] is False

    @pytest.mark.asyncio
    async def test_names_the_uploader_in_the_document_metadata(self, service, walker):
        """The username is what a reader of the document sees, so it goes in the metadata."""
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], _USERNAME, owner=_OWNER)
        assert walker.calls[0]["user_name"] == _USERNAME

    @pytest.mark.asyncio
    async def test_stamps_the_document_with_the_account_not_the_username(self, service, walker):
        """Ownership is the account id, because a username is mutable provider data.

        The document is stored under the account's own directory and matched against
        other documents of that same account, so an id is what every later read scopes
        by; a username would change under the document the day it was renamed.
        """
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], _USERNAME, owner=_OWNER)
        assert walker.calls[0]["owner"] == _OWNER

    @pytest.mark.asyncio
    async def test_refuses_an_upload_with_no_account_to_own_it(self, service, walker):
        """Otherwise the document is created in the graph belonging to nobody.

        Such a document is invisible to every account and reachable only through the
        admin CLI that assigns it, which is not what an upload asked for.
        """
        with pytest.raises(DocumentOwnershipError):
            await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], _USERNAME, owner="   ")
        assert walker.calls == []

    @pytest.mark.asyncio
    async def test_forwards_the_single_newline_flag(self, service, walker):
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER, single_newline_paragraphs=True)
        assert walker.calls[0]["single_newline_paragraphs"] is True

    @pytest.mark.asyncio
    async def test_runs_the_walker_off_the_event_loop(self, service, monkeypatch):
        """The walker is synchronous and slow; blocking here would stall every request."""
        import threading

        seen: dict[str, int] = {}

        def capture(_document_dir, *_args, **_kwargs):
            seen["thread"] = threading.get_ident()
            return []

        monkeypatch.setattr(import_service_module, "import_document_directory", capture)
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)
        assert seen["thread"] != threading.get_ident()

    @pytest.mark.asyncio
    async def test_preserves_file_bytes_exactly(self, service, monkeypatch):
        body = "Faith\r\n\x00binary\xff".encode("latin-1")
        seen: dict[str, bytes] = {}

        def capture(document_dir, *_args, **_kwargs):
            for path in Path(document_dir).rglob("*"):
                if path.is_file():
                    seen[str(path.relative_to(document_dir))] = path.read_bytes()
            return []

        monkeypatch.setattr(import_service_module, "import_document_directory", capture)
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md", body)], "abby", owner=_OWNER)
        assert seen["Act I/1.md"] == body


class TestUploadRejection:
    @pytest.mark.asyncio
    async def test_rejects_a_traversing_filename_before_writing(self, service, monkeypatch):
        def never_called(*_args, **_kwargs):
            raise AssertionError("the walker must not run for a rejected upload")

        monkeypatch.setattr(import_service_module, "import_document_directory", never_called)
        with pytest.raises(UploadRejectedError):
            await service.import_parts([FakeUpload("../../etc/passwd")], "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_rejects_one_bad_part_among_good_ones(self, service, monkeypatch):
        monkeypatch.setattr(
            import_service_module,
            "import_document_directory",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("walker must not run")),
        )
        parts = [FakeUpload("Linchpin/Act I/1.md"), FakeUpload("Linchpin/../escape.md")]
        with pytest.raises(UploadRejectedError):
            await service.import_parts(parts, "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_rejects_an_upload_over_the_byte_cap(self, service, monkeypatch):
        monkeypatch.setattr(import_service_module, "MAX_TOTAL_BYTES", 4)
        with pytest.raises(UploadTooLargeError):
            await service.import_parts([FakeUpload("Linchpin/Act I/1.md", b"far too many bytes")], "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_the_byte_cap_covers_the_whole_upload_not_one_part(self, service, monkeypatch):
        """Parts are small enough individually but add up past the cap."""
        monkeypatch.setattr(import_service_module, "MAX_TOTAL_BYTES", 10)
        monkeypatch.setattr(import_service_module, "import_document_directory", RecordingWalker())
        parts = [FakeUpload(f"Linchpin/Act I/{n}.md", b"12345") for n in range(4)]
        with pytest.raises(UploadTooLargeError):
            await service.import_parts(parts, "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_rejects_an_upload_with_too_many_files(self, service, monkeypatch):
        monkeypatch.setattr(import_service_module, "MAX_FILE_COUNT", 2)
        parts = [FakeUpload(f"Linchpin/Act I/{n}.md") for n in range(3)]
        with pytest.raises(UploadTooLargeError):
            await service.import_parts(parts, "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_rejects_a_file_named_like_another_parts_directory(self, service, monkeypatch):
        """One part is a directory the other needs: the upload is incoherent, not broken.

        The filesystem answers FileExistsError, which is our error to report as a
        server fault; what it actually means is that the caller sent a file
        where the document needs a directory.
        """
        monkeypatch.setattr(
            import_service_module,
            "import_document_directory",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("walker must not run")),
        )
        parts = [FakeUpload("Linchpin/Act I"), FakeUpload("Linchpin/Act I/1.md")]
        with pytest.raises(UploadRejectedError, match="Linchpin/Act I"):
            await service.import_parts(parts, "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_rejects_a_directory_named_like_another_parts_file(self, service, monkeypatch):
        """The same collision in the other order, which is a different OS error."""
        monkeypatch.setattr(
            import_service_module,
            "import_document_directory",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("walker must not run")),
        )
        parts = [FakeUpload("Linchpin/Act I/1.md"), FakeUpload("Linchpin/Act I")]
        with pytest.raises(UploadRejectedError, match="Linchpin/Act I"):
            await service.import_parts(parts, "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_a_path_collision_cleans_up_the_temporary_directory(self, service):
        before = set(Path(tempfile.gettempdir()).glob("dockb-import-*"))
        with pytest.raises(UploadRejectedError):
            await service.import_parts([FakeUpload("Linchpin/Act I"), FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)
        assert set(Path(tempfile.gettempdir()).glob("dockb-import-*")) == before

    @pytest.mark.asyncio
    async def test_a_filesystem_failure_that_is_not_a_path_collision_stays_ours(self, service, monkeypatch):
        """A full disk or a vanished temp dir is our fault, not the caller's upload."""
        monkeypatch.setattr(import_service_module.Path, "mkdir", MagicMock(side_effect=OSError(28, "No space left on device")))
        with pytest.raises(OSError):
            await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)

    @pytest.mark.asyncio
    async def test_the_file_cap_is_the_documented_one(self):
        assert MAX_FILE_COUNT == 2_000

    @pytest.mark.asyncio
    async def test_the_cap_is_the_documented_one(self):
        """The cap the service enforces is the published limit, not a private one."""
        assert MAX_TOTAL_BYTES == 64 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_rejects_an_empty_upload(self, service):
        with pytest.raises(UploadRejectedError, match="no files"):
            await service.import_parts([], "abby", owner=_OWNER)


class TestTemporaryDirectory:
    @pytest.mark.asyncio
    async def test_is_removed_after_a_successful_import(self, service, walker):
        before = set(Path(tempfile.gettempdir()).glob("dockb-import-*"))
        await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)
        assert set(Path(tempfile.gettempdir()).glob("dockb-import-*")) == before

    @pytest.mark.asyncio
    async def test_is_removed_when_the_walker_fails(self, service, monkeypatch):
        monkeypatch.setattr(
            import_service_module,
            "import_document_directory",
            RecordingWalker(raises=DocumentFormatError("Chapter file is not numbered")),
        )
        before = set(Path(tempfile.gettempdir()).glob("dockb-import-*"))
        with pytest.raises(DocumentFormatError, match="not numbered"):
            await service.import_parts([FakeUpload("Linchpin/Act I/1.md")], "abby", owner=_OWNER)
        assert set(Path(tempfile.gettempdir()).glob("dockb-import-*")) == before
