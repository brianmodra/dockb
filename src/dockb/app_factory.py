"""Application factory — builds a configured FastAPI instance.

Call ``create_app()`` to get a FastAPI app with all routers and middleware
registered.  Service wiring is handled separately by ``composition.wire()``.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from dockb.controllers.app_state import router as app_state_router
from dockb.controllers.auth import get_current_user
from dockb.controllers.auth import router as auth_router
from dockb.controllers.chapters import router as chapters_router
from dockb.controllers.documents import router as documents_router
from dockb.controllers.history import router as history_router
from dockb.controllers.imports import router as imports_router
from dockb.controllers.notifications import router as notifications_router
from dockb.controllers.paragraphs import router as paragraphs_router
from dockb.controllers.sentences import router as sentences_router
from dockb.editor_shell import mount_editor_shell
from dockb.timing import TimingMiddleware

# The manuscript routers serve the editor and are gated on the session identity.
# `auth` stays open — it is how a caller obtains a session — and `app_state`
# carries the gate on its own routes, because each needs the resolved username.
# `get_current_user` raises 401 when login is required and no valid cookie is
# presented, and falls back to the local OS identity in local mode.
_authenticated = (Depends(get_current_user),)


def create_app() -> FastAPI:
    """Create and return a FastAPI application with all routers and middleware."""
    application = FastAPI(title="DockB")
    application.add_middleware(GZipMiddleware, minimum_size=500)
    application.add_middleware(TimingMiddleware)
    application.include_router(documents_router, dependencies=_authenticated)
    application.include_router(auth_router)
    application.include_router(app_state_router)
    application.include_router(chapters_router, dependencies=_authenticated)
    application.include_router(paragraphs_router, dependencies=_authenticated)
    application.include_router(sentences_router, dependencies=_authenticated)
    application.include_router(history_router, dependencies=_authenticated)
    application.include_router(notifications_router, dependencies=_authenticated)
    application.include_router(imports_router, dependencies=_authenticated)
    # The editor is served from here rather than loaded from file://, so it is
    # same-origin with /api. That is what lets the SameSite=lax session cookie
    # reach the manuscript routes, and it means no CORS grant is needed — or
    # wanted: one for the file:// "null" origin would let any local file page
    # read the API as the signed-in user. Mounted last, and under its own
    # prefix, so it cannot shadow a route above.
    mount_editor_shell(application)
    return application
