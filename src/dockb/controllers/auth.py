"""Auth flow routes: the login URL and the loopback callback.

``GET /api/auth/login?provider=google`` returns the provider's consent URL.
``GET /callback`` is the loopback redirect target the provider sends the code to;
it completes the login and sets the HttpOnly session cookie, then renders a small
HTML success or error page for the browser tab. See ``README_auth.md`` §6.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from dockb.services.auth_service import InvalidLoginStateError, UnknownProviderError

router = APIRouter(tags=["auth"])

_auth_service: Any = None

_SESSION_COOKIE = "dockb_session"

_PAGE_CSS = """
body { font-family: system-ui, sans-serif; background: #f6f6f4; color: #222; margin: 0;
       display: flex; align-items: center; justify-content: center; height: 100vh; }
.card { background: #fff; padding: 2rem 2.5rem; border-radius: 12px;
        box-shadow: 0 1px 4px rgba(0,0,0,.12); text-align: center; max-width: 32rem; }
"""

_SUCCESS_PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Signed in</title><style>{_PAGE_CSS}</style></head>
<body><div class="card"><h2>You're signed in</h2><p>Close this tab and return to DockB.</p></div></body></html>"""


def _error_page(message: str) -> str:
    """Render the error page, escaping *message* (browser-controlled text)."""
    safe_message = html.escape(message)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sign-in failed</title><style>{_PAGE_CSS}</style></head>
<body><div class="card"><h2>Sign-in failed</h2><p>{safe_message}</p></div></body></html>"""


def get_auth_service() -> Any:
    return _auth_service


def set_auth_service(service: Any) -> None:
    global _auth_service  # noqa: PLW0603
    _auth_service = service


@router.get("/api/auth/login")
def auth_login(
    provider: str = Query(..., description="OAuth provider name, e.g. google or github"),
    svc: Any = Depends(get_auth_service),
) -> dict[str, str]:
    if svc is None:
        raise HTTPException(status_code=503, detail="auth_service_unavailable")
    try:
        authorization_url = svc.begin_login(provider)
    except UnknownProviderError as exc:
        raise HTTPException(status_code=400, detail=f"unsupported_provider: {exc}") from exc
    return {"authorization_url": authorization_url}


@router.get("/callback")
def auth_callback(
    code: str = Query(""),
    state: str = Query(""),
    error: str | None = Query(None),
    svc: Any = Depends(get_auth_service),
) -> HTMLResponse:
    if svc is None:
        return HTMLResponse(_error_page("The backend is not ready. Try again shortly."), status_code=503)
    if error:
        return HTMLResponse(_error_page(f"The provider reported a problem: {error}"))
    try:
        user_id = svc.complete_login(state=state, code=code)
    except InvalidLoginStateError as exc:
        return HTMLResponse(_error_page(f"Sign-in could not be completed ({exc}). Please try again."))
    token = svc.session_cookie(user_id)
    response = HTMLResponse(_SUCCESS_PAGE)
    response.set_cookie(_SESSION_COOKIE, token, max_age=svc.session_ttl_seconds, httponly=True, samesite="lax", path="/")
    return response


def get_current_user(
    request: Request,
    svc: Any = Depends(get_auth_service),
) -> str:
    """Resolve the authenticated username from the session cookie.

    In OAuth mode a valid cookie is required (401 without it). In local mode — no
    provider configured — the identity is the OS username and no cookie is needed;
    the local ``users`` row is created lazily.
    """
    if svc is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    token = request.cookies.get(_SESSION_COOKIE, "")
    user_id: str | None = svc.authenticate_cookie(token)
    if user_id is None and svc.requires_login:
        raise HTTPException(status_code=401, detail="not_authenticated")
    if user_id is None:
        user_id = svc.ensure_local_user(svc.local_username())
    return user_id


def get_current_session_context(
    user_id: str = Depends(get_current_user),
    svc: Any = Depends(get_auth_service),
) -> Any:
    """Resolve the user's live SessionContext (401 when the server session is gone)."""
    ctx = svc.session_for(user_id)
    if ctx is None:
        raise HTTPException(status_code=401, detail="session_expired_relogin")
    return ctx


@router.get("/api/auth/me")
def auth_me(
    user_id: str = Depends(get_current_user),
    svc: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    profile = svc.get_user(user_id)
    if profile is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return {
        "user": {
            "id": profile["id"],
            "username": profile["username"],
            "email": profile["email"],
            "display_name": profile["display_name"],
            "avatar_url": profile["avatar_url"],
        }
    }
