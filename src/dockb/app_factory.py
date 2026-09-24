"""Application factory — builds a configured FastAPI instance.

Call ``create_app()`` to get a FastAPI app with all routers and middleware
registered.  Service wiring is handled separately by ``composition.wire()``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from dockb.controllers.app_state import router as app_state_router
from dockb.controllers.auth import router as auth_router
from dockb.controllers.chapters import router as chapters_router
from dockb.controllers.documents import router as documents_router
from dockb.controllers.history import router as history_router
from dockb.controllers.notifications import router as notifications_router
from dockb.controllers.paragraphs import router as paragraphs_router
from dockb.controllers.sentences import router as sentences_router

# The Electron shell loads the built renderer from file://, whose Origin is the
# literal "null"; served development flows arrive from the Vite dev server.
_CORS_ORIGINS = ["null", "http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    """Create and return a FastAPI application with all routers and middleware."""
    application = FastAPI(title="DockB")
    application.add_middleware(GZipMiddleware, minimum_size=500)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(documents_router)
    application.include_router(auth_router)
    application.include_router(app_state_router)
    application.include_router(chapters_router)
    application.include_router(paragraphs_router)
    application.include_router(sentences_router)
    application.include_router(history_router)
    application.include_router(notifications_router)
    return application
