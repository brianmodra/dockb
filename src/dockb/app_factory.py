"""Application factory — builds a configured FastAPI instance.

Call ``create_app()`` to get a FastAPI app with all routers and middleware
registered.  Service wiring is handled separately by ``composition.wire()``.
"""

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from dockb.controllers.chapters import router as chapters_router
from dockb.controllers.documents import router as documents_router
from dockb.controllers.history import router as history_router
from dockb.controllers.notifications import router as notifications_router
from dockb.controllers.paragraphs import router as paragraphs_router
from dockb.controllers.sentences import router as sentences_router


def create_app() -> FastAPI:
    """Create and return a FastAPI application with all routers and middleware."""
    application = FastAPI(title="DockB")
    application.add_middleware(GZipMiddleware, minimum_size=500)
    application.include_router(documents_router)
    application.include_router(chapters_router)
    application.include_router(paragraphs_router)
    application.include_router(sentences_router)
    application.include_router(history_router)
    application.include_router(notifications_router)
    return application
