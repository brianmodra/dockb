"""Tests for application factory and composition root.

``create_app`` builds a FastAPI instance with all routers and middleware.
``wire`` connects repositories, services, and route handlers at startup.
"""

# pylint: disable=unused-argument

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
