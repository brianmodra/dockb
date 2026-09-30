"""Tests for the multipart upload's path and size rules.

A multipart filename is chosen by the caller, so every rule here is a security
boundary: a name that slips through becomes a path the server writes.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from dockb.uploads import (
    UploadBudget,
    UploadRejectedError,
    UploadTooLargeError,
    document_root,
    resolve_inside,
    validate_part_path,
)


class TestValidatePartPath:
    @pytest.mark.parametrize(
        "filename",
        [
            "Linchpin/Act I/Chapter 1.md",
            "Linchpin/document_metadata.yaml",
            "Linchpin/Act I/Characters/Jael.md",
            "Linchpin/Act I/deeply/nested/file.md",
            "Linchpin/Act 1/Chapter 1",
        ],
    )
    def test_accepts_a_relative_document_path(self, filename):
        assert validate_part_path(filename) == PurePosixPath(filename)

    @pytest.mark.parametrize(
        "filename",
        [
            "../../etc/passwd",
            "Linchpin/../../etc/passwd",
            "..",
            "../",
            "Linchpin/..",
            "./Linchpin/Chapter 1.md",
            "Linchpin/./Chapter 1.md",
        ],
    )
    def test_rejects_a_traversing_path(self, filename):
        with pytest.raises(UploadRejectedError, match="segment|relative"):
            validate_part_path(filename)

    @pytest.mark.parametrize("filename", ["/etc/passwd", "/Linchpin/Chapter 1.md", "//Linchpin/x.md"])
    def test_rejects_an_absolute_path(self, filename):
        with pytest.raises(UploadRejectedError, match="relative"):
            validate_part_path(filename)

    @pytest.mark.parametrize(
        "filename",
        ["Linchpin\\Act I\\Chapter 1.md", "..\\..\\etc\\passwd", "C:\\Windows\\system.ini", "C:/Windows/system.ini", "d:x"],
    )
    def test_rejects_a_windows_style_name(self, filename):
        with pytest.raises(UploadRejectedError, match="separator|drive"):
            validate_part_path(filename)

    @pytest.mark.parametrize("filename", ["Linchpin/Chapter\x001.md", "Linchpin/Chapter\n1.md", "Linchpin/\x7f.md"])
    def test_rejects_control_characters(self, filename):
        with pytest.raises(UploadRejectedError, match="control characters"):
            validate_part_path(filename)

    @pytest.mark.parametrize("filename", [None, ""])
    def test_rejects_a_missing_name(self, filename):
        with pytest.raises(UploadRejectedError, match="no filename|empty"):
            validate_part_path(filename)

    def test_rejects_a_path_that_is_only_a_separator(self):
        with pytest.raises(UploadRejectedError):
            validate_part_path("/")


class TestResolveInside:
    def test_places_a_file_under_the_base(self, tmp_path):
        target = resolve_inside(tmp_path, PurePosixPath("Act I/Chapter 1.md"))
        assert target == tmp_path / "Act I" / "Chapter 1.md"

    def test_refuses_a_symlink_that_points_outside(self, tmp_path):
        """A name can be well-formed and still land outside, through a symlink."""
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        base = tmp_path / "upload"
        base.mkdir()
        (base / "link").symlink_to(outside)
        with pytest.raises(UploadRejectedError, match="escapes"):
            resolve_inside(base, PurePosixPath("link/secret.txt"))

    def test_allows_a_symlink_that_stays_inside(self, tmp_path):
        base = tmp_path / "upload"
        (base / "real").mkdir(parents=True)
        (base / "link").symlink_to(base / "real")
        assert resolve_inside(base, PurePosixPath("link/Chapter 1.md")) == base / "real" / "Chapter 1.md"


class TestDocumentRoot:
    def test_is_the_shared_top_level_directory(self):
        names = [validate_part_path(n) for n in ("Linchpin/Act I/1.md", "Linchpin/metadata.yaml")]
        assert document_root(names) == "Linchpin"

    def test_rejects_files_from_two_directories(self):
        names = [validate_part_path(n) for n in ("Linchpin/Act I/1.md", "Faith/Act I/1.md")]
        with pytest.raises(UploadRejectedError, match="one document directory"):
            document_root(names)

    def test_rejects_files_with_no_directory(self):
        names = [validate_part_path(n) for n in ("Chapter 1.md", "Chapter 2.md")]
        with pytest.raises(UploadRejectedError, match="inside a document directory"):
            document_root(names)

    def test_rejects_a_mix_of_bare_and_nested(self):
        names = [validate_part_path(n) for n in ("Chapter 1.md", "Linchpin/Chapter 2.md")]
        with pytest.raises(UploadRejectedError, match="inside a document directory"):
            document_root(names)

    def test_rejects_an_empty_upload(self):
        with pytest.raises(UploadRejectedError, match="no files"):
            document_root([])


class TestUploadBudget:
    def test_accepts_an_upload_at_the_cap(self):
        budget = UploadBudget(10)
        budget.charge(4)
        budget.charge(6)

    def test_rejects_charging_past_the_cap(self):
        budget = UploadBudget(10)
        budget.charge(8)
        with pytest.raises(UploadTooLargeError, match="too large"):
            budget.charge(3)

    def test_the_cap_covers_every_part_drawn_against_it(self):
        """Two parts that each fit can still add up past the cap."""
        budget = UploadBudget(10)
        budget.charge(6)
        with pytest.raises(UploadTooLargeError):
            budget.charge(6)

    def test_a_rejected_charge_is_not_spent(self):
        """A refused part must not push the rest of the upload over as well."""
        budget = UploadBudget(10)
        budget.charge(8)
        with pytest.raises(UploadTooLargeError):
            budget.charge(3)
        budget.charge(2)

    def test_a_size_rejection_is_also_an_upload_rejection(self):
        """The route tells 413 from 422 by type, so the subclass must hold."""
        with pytest.raises(UploadRejectedError):
            UploadBudget(1).charge(2)
