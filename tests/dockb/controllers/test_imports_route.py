"""Tests for POST /api/import — the multipart import route."""

# pylint: disable=unused-argument,too-few-public-methods

from __future__ import annotations

import io

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from dockb.controllers.auth import get_auth_service, get_current_user
from dockb.controllers.imports import router, set_import_service
from dockb.exceptions import ChapterMismatchError, DocumentFormatError
from dockb.services.markdown_import import ChapterImportSummary
from dockb.uploads import MAX_TOTAL_BYTES, UploadRejectedError, UploadTooLargeError


class StubImportService:
    """Records the arguments the route passes, and returns a fixed result."""

    def __init__(self, summaries=None, raises: Exception | None = None) -> None:
        self.summaries = (
            summaries
            if summaries is not None
            else [ChapterImportSummary(chapter_id="c1", created=True, title="Opening 1", category="Chapter")]
        )
        self.raises = raises
        self.calls: list[dict[str, object]] = []

    async def import_parts(self, parts, user_name, *, owner, single_newline_paragraphs=False):
        self.calls.append(
            {
                "parts": parts,
                "user_name": user_name,
                "owner": owner,
                "single_newline_paragraphs": single_newline_paragraphs,
            }
        )
        if self.raises is not None:
            raise self.raises
        return self.summaries


class StubAuthService:
    """Stands in for the account store the route reads the username from."""

    def get_user(self, owner: str) -> dict[str, str]:
        return {"id": owner, "username": "abby"}


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="not_authenticated")


@pytest.fixture(autouse=True)
def _isolated_import_service():
    """The service is a module-level singleton, so each test sets and clears it."""
    yield
    set_import_service(None)


def _app(svc: StubImportService | None = None, *, signed_in: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = (lambda: "acct-1") if signed_in else (lambda: (_ for _ in ()).throw(_unauthenticated()))
    app.dependency_overrides[get_auth_service] = StubAuthService
    set_import_service(svc or StubImportService())
    return app


def _files(**parts: str):
    return [("files", (name, io.BytesIO(content.encode()), "text/markdown")) for name, content in parts.items()]


class TestImportRoute:
    def test_returns_one_summary_per_imported_chapter(self):
        client = TestClient(_app())
        response = client.post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert response.status_code == 200
        assert response.json() == {
            "imports": [
                {
                    "chapter_id": "c1",
                    "title": "Opening 1",
                    "category": "Chapter",
                    "created": True,
                    "changed": 0,
                    "added": 0,
                    "deleted": 0,
                }
            ]
        }

    def test_takes_the_user_from_the_session_not_the_body(self):
        svc = StubImportService()
        client = TestClient(_app(svc))
        client.post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert svc.calls[0]["user_name"] == "abby"
        assert svc.calls[0]["owner"] == "acct-1"

    def test_forwards_the_single_newline_flag(self):
        svc = StubImportService()
        client = TestClient(_app(svc))
        client.post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}), data={"single_newline_paragraphs": "true"})
        assert svc.calls[0]["single_newline_paragraphs"] is True

    def test_defaults_the_single_newline_flag_to_false(self):
        svc = StubImportService()
        client = TestClient(_app(svc))
        client.post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert svc.calls[0]["single_newline_paragraphs"] is False

    def test_requires_files(self):
        assert TestClient(_app()).post("/api/import").status_code == 422


class TestImportRouteErrors:
    @pytest.mark.parametrize(
        ("raises", "status", "fragment"),
        [
            (UploadRejectedError("filename must be relative: '/etc/passwd'"), 422, "relative"),
            (DocumentFormatError("Chapter file 'x' is not numbered"), 422, "not numbered"),
            (ChapterMismatchError("Chapter 'c1' from 'x.md' is not a child of document 'd1'"), 422, "not a child"),
            (UploadTooLargeError("upload too large"), 413, "too large"),
            (UploadTooLargeError("too many files"), 413, "too many files"),
        ],
    )
    def test_maps_a_service_failure_to_a_status(self, raises, status, fragment):
        response = TestClient(_app(StubImportService(raises=raises))).post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert response.status_code == status
        assert fragment in response.json()["detail"]

    def test_a_plain_value_error_is_a_server_fault_not_a_bad_document(self):
        """Only a named document error is the caller's fault; a bare ValueError is ours.

        The route must not turn an internal bug into a 422 "your document is
        wrong", so a ValueError that is not a DocumentFormatError is left to
        surface as a 500.
        """
        client = TestClient(_app(StubImportService(raises=ValueError("invalid literal for int()"))), raise_server_exceptions=False)
        response = client.post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert response.status_code == 500

    def test_a_capped_upload_is_413_even_though_it_is_a_rejection(self):
        """Both caps answer 413; a client must not have to read the message to tell."""
        response = TestClient(_app(StubImportService(raises=UploadTooLargeError("too many files")))).post(
            "/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"})
        )
        assert response.status_code == 413

    def test_reports_an_unwired_service(self):
        set_import_service(None)
        app = _app()
        set_import_service(None)
        response = TestClient(app).post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert response.status_code == 503


class TestImportRouteIsGated:
    def test_refuses_an_anonymous_caller(self):
        svc = StubImportService()
        response = TestClient(_app(svc, signed_in=False)).post("/api/import", files=_files(**{"Linchpin/Act I/1.md": "a"}))
        assert response.status_code == 401
        assert not svc.calls

    def test_is_registered_behind_the_session_gate(self):
        """The gate is registered on the route, so it is not a per-handler habit."""
        from dockb.app_factory import create_app

        routes = [r for r in create_app().routes if getattr(r, "path", None) == "/api/import"]
        assert routes, "the import route is not registered"
        assert any(d.call is get_current_user for d in routes[0].dependant.dependencies)


def test_byte_cap_is_published():
    assert MAX_TOTAL_BYTES == 64 * 1024 * 1024
