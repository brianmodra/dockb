"""Tests for application factory and composition root.

``create_app`` builds a FastAPI instance with all routers and middleware.
``wire`` connects repositories, services, and route handlers at startup.
"""

# pylint: disable=unused-argument,too-few-public-methods

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


class TestCreateApp:
    """create_app returns a fully configured FastAPI instance."""

    def test_returns_fastapi(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

    def test_has_gzip_middleware(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        from fastapi.middleware.gzip import GZipMiddleware

        middleware_classes = [m.cls for m in app.user_middleware]
        assert GZipMiddleware in middleware_classes

    def test_cors_middleware_allows_the_desktop_client(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        from fastapi.middleware.cors import CORSMiddleware

        cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        assert cors.kwargs["allow_credentials"] is True
        assert set(cors.kwargs["allow_origins"]) == {
            "null",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        }

    def test_cors_headers_on_responses_to_the_file_origin(self) -> None:
        from fastapi.testclient import TestClient

        from dockb.app_factory import create_app

        client = TestClient(create_app())
        response = client.get("/api/auth/login", headers={"Origin": "null"})
        assert response.headers["access-control-allow-origin"] == "null"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_all_crud_routers_registered(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        routes = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/documents" in routes or "/api/documents/{document_id}" in routes
        assert "/api/chapters" in routes or "/api/chapters/{chapter_id}" in routes
        assert "/api/paragraphs" in routes or "/api/paragraphs/{paragraph_id}" in routes
        assert "/api/sentences" in routes or "/api/sentences/{sentence_id}" in routes

    def test_history_router_registered(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        routes = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/history/{chapter_id}" in routes

    def test_notifications_router_registered(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        routes = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/notifications" in routes

    def test_auth_routers_registered(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        routes = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/auth/login" in routes
        assert "/callback" in routes
        assert "/api/auth/me" in routes

    def test_app_state_router_registered(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        routes = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/app/state" in routes

    def test_all_http_methods_present(self) -> None:
        from dockb.app_factory import create_app

        app = create_app()
        method_path_pairs = {(r.path, frozenset(r.methods)) for r in app.routes if hasattr(r, "methods")}
        assert ("/api/documents", frozenset({"GET"})) in method_path_pairs
        assert ("/api/documents", frozenset({"POST"})) in method_path_pairs
        assert ("/api/documents/{document_id}", frozenset({"GET"})) in method_path_pairs
        assert ("/api/documents/{document_id}", frozenset({"PUT"})) in method_path_pairs
        assert ("/api/documents/{document_id}", frozenset({"DELETE"})) in method_path_pairs
        assert ("/api/notifications", frozenset({"GET"})) in method_path_pairs


# ---------------------------------------------------------------------------
# Composition — wire / unwire
# ---------------------------------------------------------------------------


class TestWireFunction:
    """wire() connects infrastructure to route-level DI globals."""

    def test_wire_exists(self) -> None:
        from dockb.composition import wire

        assert callable(wire)

    def test_unwire_exists(self) -> None:
        from dockb.composition import unwire

        assert callable(unwire)


class TestWireServices:
    """wire() creates and injects real service instances into route modules."""

    def setup_method(self) -> None:
        from dockb.controllers.chapters import set_ch_service
        from dockb.controllers.documents import set_doc_service
        from dockb.controllers.history import set_history_service
        from dockb.controllers.notifications import set_session_context
        from dockb.controllers.paragraphs import set_para_service
        from dockb.controllers.sentences import set_sent_service

        set_doc_service(None)
        set_ch_service(None)
        set_para_service(None)
        set_sent_service(None)
        set_history_service(None)
        set_session_context(None)

    def teardown_method(self) -> None:
        from dockb.controllers.chapters import set_ch_service
        from dockb.controllers.documents import set_doc_service
        from dockb.controllers.history import set_history_service
        from dockb.controllers.notifications import set_session_context
        from dockb.controllers.paragraphs import set_para_service
        from dockb.controllers.sentences import set_sent_service

        set_doc_service(None)
        set_ch_service(None)
        set_para_service(None)
        set_sent_service(None)
        set_history_service(None)
        set_session_context(None)

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_sets_all_services(
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
    ) -> None:
        from dockb.composition import wire
        from dockb.controllers.chapters import get_ch_service
        from dockb.controllers.documents import get_doc_service
        from dockb.controllers.paragraphs import get_para_service
        from dockb.controllers.sentences import get_sent_service

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf)

        assert get_doc_service() is not None
        assert get_ch_service() is not None
        assert get_para_service() is not None
        assert get_sent_service() is not None

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_sets_session_context(
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
    ) -> None:
        from dockb.composition import wire
        from dockb.controllers.notifications import get_session_context

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf)

        ctx = get_session_context()
        assert ctx is not None

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_sets_history_service(
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
        tmp_path,
    ) -> None:
        from dockb.composition import wire
        from dockb.controllers.history import get_history_service

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf, snapshot_base_dir=tmp_path)

        assert get_history_service() is not None

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_passes_document_store_to_doc_service(
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
        tmp_path,
    ) -> None:
        from dockb.composition import wire
        from dockb.controllers.documents import get_doc_service

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf, document_base_dir=tmp_path)

        svc = get_doc_service()
        assert svc._document_store is not None  # pylint: disable=protected-access

    def test_unwire_clears_services(self) -> None:
        from dockb.composition import unwire
        from dockb.controllers.chapters import get_ch_service
        from dockb.controllers.documents import get_doc_service
        from dockb.controllers.history import get_history_service
        from dockb.controllers.paragraphs import get_para_service
        from dockb.controllers.sentences import get_sent_service

        unwire()

        assert get_doc_service() is None
        assert get_ch_service() is None
        assert get_para_service() is None
        assert get_sent_service() is None
        assert get_history_service() is None

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_injects_auth_service_when_secret_present(
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
        tmp_path,
        monkeypatch,
    ) -> None:
        from dockb.composition import unwire, wire
        from dockb.controllers.auth import get_auth_service
        from dockb.services.auth_service import AuthService

        monkeypatch.setenv("DOCKB_SECRET_KEY", "test-secret")
        monkeypatch.setenv("OAUTH_GITHUB_CLIENT_ID", "gh-id")
        monkeypatch.setenv("OAUTH_GITHUB_CLIENT_SECRET", "gh-secret")
        monkeypatch.setenv("OAUTH_SESSION_TTL_HOURS", "2")

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf, document_base_dir=tmp_path)
        try:
            svc = get_auth_service()
            assert isinstance(svc, AuthService)
            assert svc.requires_login is True
            assert svc.providers == ["github"]
        finally:
            unwire()
        assert get_auth_service() is None

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_injects_local_mode_auth_service_without_secret(
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
        tmp_path,
        monkeypatch,
    ) -> None:
        from dockb.composition import unwire, wire
        from dockb.controllers.auth import get_auth_service
        from dockb.services.auth_service import AuthService

        monkeypatch.delenv("DOCKB_SECRET_KEY", raising=False)
        monkeypatch.delenv("OAUTH_GITHUB_CLIENT_ID", raising=False)
        monkeypatch.delenv("OAUTH_GITHUB_CLIENT_SECRET", raising=False)

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf, document_base_dir=tmp_path)
        try:
            svc = get_auth_service()
            assert isinstance(svc, AuthService)
            assert svc.requires_login is False
            assert svc.providers == []
        finally:
            unwire()
        assert get_auth_service() is None

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_local_mode_me_and_app_state_work_without_a_secret(  # pylint: disable=too-many-locals
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
        tmp_path,
        monkeypatch,
    ) -> None:
        from fastapi.testclient import TestClient

        from dockb.app_factory import create_app
        from dockb.composition import unwire, wire

        monkeypatch.delenv("DOCKB_SECRET_KEY", raising=False)
        monkeypatch.delenv("OAUTH_GITHUB_CLIENT_ID", raising=False)
        monkeypatch.delenv("OAUTH_GITHUB_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "google-id")
        monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "google-secret")
        monkeypatch.setenv("USER", "dave")

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf, document_base_dir=tmp_path)
        try:
            client = TestClient(create_app())
            me = client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json()["user"]["username"] == "dave"

            state = client.get("/api/app/state")
            assert state.status_code == 200
            put = client.put("/api/app/state", json={"last_document_id": "d1"})
            assert put.status_code == 200
            assert put.json()["last_document_id"] == "d1"
        finally:
            unwire()

    @patch("dockb.composition.DocumentRepository")
    @patch("dockb.composition.ChapterRepository")
    @patch("dockb.composition.ParagraphRepository")
    @patch("dockb.composition.SentenceRepository")
    @patch("dockb.composition.UnitOfWorkFactory")
    def test_wire_accounts_base_dir_enables_local_mode_me_and_app_state(  # pylint: disable=too-many-locals
        self,
        mock_uow_factory: MagicMock,
        mock_sent_repo: MagicMock,
        mock_para_repo: MagicMock,
        mock_ch_repo: MagicMock,
        mock_doc_repo: MagicMock,
        tmp_path,
        monkeypatch,
    ) -> None:
        from fastapi.testclient import TestClient

        from dockb.app_factory import create_app
        from dockb.composition import unwire, wire

        monkeypatch.delenv("DOCKB_SECRET_KEY", raising=False)
        monkeypatch.delenv("OAUTH_GITHUB_CLIENT_ID", raising=False)
        monkeypatch.delenv("OAUTH_GITHUB_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("USER", "dave")

        mock_sf = MagicMock()
        mock_sf.session.return_value.__enter__ = MagicMock(return_value=MagicMock())

        wire(mock_sf, accounts_base_dir=tmp_path)
        try:
            client = TestClient(create_app())
            me = client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json()["user"]["username"] == "dave"

            put = client.put("/api/app/state", json={"last_document_id": "d1"})
            assert put.status_code == 200
            assert client.get("/api/app/state").json()["last_document_id"] == "d1"
        finally:
            unwire()


class TestResolveDocumentBaseDir:
    """resolve_document_base_dir provisions the server-owned markdown tree."""

    def test_defaults_to_cwd_dockb_chapters_dir_and_git_inits_it(self, tmp_path, monkeypatch) -> None:
        from pathlib import Path

        from dockb.composition import resolve_document_base_dir

        monkeypatch.delenv("DOCKB_CHAPTERS_DIR", raising=False)
        monkeypatch.chdir(tmp_path)

        base = resolve_document_base_dir()

        expected = Path(tmp_path) / "dockb_chapters_dir"
        assert base == expected
        assert base.is_dir()
        assert (base / ".git").is_dir()

    def test_uses_configured_dir_and_git_inits_when_missing(self, tmp_path, monkeypatch) -> None:
        from dockb.composition import resolve_document_base_dir

        target = tmp_path / "chapters"
        monkeypatch.setenv("DOCKB_CHAPTERS_DIR", str(target))

        base = resolve_document_base_dir()

        assert base == target
        assert base.is_dir()
        assert (base / ".git").is_dir()

    def test_returns_existing_dir_without_clobbering(self, tmp_path, monkeypatch) -> None:

        from dockb.composition import resolve_document_base_dir

        existing = tmp_path / "chapters"
        existing.mkdir()
        marker = existing / "keep.txt"
        marker.write_text("hello", encoding="utf-8")

        base = resolve_document_base_dir(existing)

        assert base == existing
        assert marker.read_text(encoding="utf-8") == "hello"


# ---------------------------------------------------------------------------
# Request timing middleware
# ---------------------------------------------------------------------------


class TestTimingMiddleware:
    """TimingMiddleware logs a per-request total plus a stage breakdown."""

    def test_timing_middleware_registered_outermost(self) -> None:
        from dockb.app_factory import create_app
        from dockb.timing import TimingMiddleware

        app = create_app()
        middleware_classes = [m.cls for m in app.user_middleware]
        assert middleware_classes[0] is TimingMiddleware

    def test_request_logs_total_and_stage_breakdown(self, caplog) -> None:
        # The chapter-document route is a sync ``def``, so FastAPI runs it in a
        # threadpool: this exercises stage accumulation across that hop.
        import logging
        import re
        import time

        from fastapi.testclient import TestClient

        from dockb.app_factory import create_app
        from dockb.controllers.chapters import set_ch_service
        from dockb.timing import measure

        class FakeChapterService:
            def open_document(self, chapter_id: str) -> str | None:
                with measure("fake.slow_stage"):
                    time.sleep(0.005)
                return "canonical text"

        set_ch_service(FakeChapterService())
        try:
            caplog.set_level(logging.INFO, logger="dockb.timing")
            client = TestClient(create_app())
            response = client.get("/api/chapters/c1/document")
            assert response.status_code == 200
            lines = [r.message for r in caplog.records if r.name == "dockb.timing"]
            assert any(
                re.match(
                    r"^request GET /api/chapters/c1/document 200 \d+ms \| fake.slow_stage \d+ms$",
                    line,
                )
                for line in lines
            )
        finally:
            set_ch_service(None)

    def test_request_without_stages_logs_total_only(self, caplog) -> None:
        import logging
        import re

        from fastapi.testclient import TestClient

        from dockb.app_factory import create_app
        from dockb.controllers.chapters import set_ch_service

        class QuietService:
            def open_document(self, chapter_id: str) -> str | None:
                return "text"

        set_ch_service(QuietService())
        try:
            caplog.set_level(logging.INFO, logger="dockb.timing")
            client = TestClient(create_app())
            response = client.get("/api/chapters/c1/document")
            assert response.status_code == 200
            lines = [r.message for r in caplog.records if r.name == "dockb.timing"]
            assert any(re.match(r"^request GET /api/chapters/c1/document 200 \d+ms$", line) for line in lines)
        finally:
            set_ch_service(None)

    def test_raised_exception_logs_status_500(self, caplog) -> None:
        import logging
        import re

        from fastapi.testclient import TestClient

        from dockb.app_factory import create_app
        from dockb.controllers.chapters import set_ch_service

        class FailingService:
            def open_document(self, chapter_id: str) -> str | None:
                raise RuntimeError("boom")

        set_ch_service(FailingService())
        try:
            caplog.set_level(logging.INFO, logger="dockb.timing")
            client = TestClient(create_app(), raise_server_exceptions=False)
            response = client.get("/api/chapters/c1/document")
            assert response.status_code == 500
            lines = [r.message for r in caplog.records if r.name == "dockb.timing"]
            assert any(re.match(r"^request GET /api/chapters/c1/document 500 \d+ms$", line) for line in lines)
        finally:
            set_ch_service(None)
