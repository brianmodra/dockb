"""Auth flow routes: the login URL, password sign-in, and the loopback callback.

``GET /api/auth/login?provider=google`` returns the provider's consent URL.
``GET /callback`` is the loopback redirect target the provider sends the code to;
it completes the login and sets the HttpOnly session cookie, then renders a small
HTML success or error page for the browser tab. See ``README_auth.md`` §6.

``POST /api/auth/login/password`` signs in with a username and password, and
``POST /api/auth/change-password`` replaces one after proving the current one.
Argon2 runs at ~46 MiB and ~80 ms, so both are handed to the threadpool rather than
run on the event loop. See ``README_auth.md`` §7.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from dockb.controllers.schemas.auth import (
    ChangePasswordRequest,
    PasswordLoginRequest,
)
from dockb.passwords import PasswordPolicyError
from dockb.services.auth_service import (
    InvalidLoginStateError,
    LoginFailedError,
    PasswordUnchangedError,
    RateLimitedError,
    UnknownProviderError,
)

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


def _set_session_cookie(response: Response, token: str, max_age: int) -> None:
    """Attach the session cookie, shared by both ways in.

    ``HttpOnly`` keeps it away from the editor's JavaScript, and it is scoped to
    ``/api`` so it is sent to the routes that authenticate it and withheld from
    everything else the server serves, including ``/callback`` and the docs.

    ``SameSite=Strict`` closes the form-post CSRF hole for password sign-in, where
    there is no ``state`` or PKCE to protect the request. The OAuth callback is a
    top-level navigation to a loopback URL on this same origin, so it is still
    sent; and the editor is served same-origin from ``/editor/`` rather than from
    ``file://``, which is what lets a same-site cookie reach the manuscript routes
    at all.
    """
    response.set_cookie(_SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="strict", path="/api")


def _caller_ip(request: Request) -> str:
    """The address used to throttle a sign-in, and nothing else.

    The transport's peer address, not a forwarded header: ``X-Forwarded-For`` is
    caller-controlled, so trusting it would let anyone mint a fresh throttle
    allowance per attempt by inventing a value. DockB is a local server and is not
    expected to sit behind a proxy; a deployment that does should terminate the
    proxy and rate limit there instead.
    """
    return request.client.host if request.client is not None else ""


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


@router.get("/api/auth/config")
def auth_config(
    svc: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    """Describe the available ways in, so the editor can render a password form.

    ``login_required`` is constant: no configuration makes this false, because there is
    no way to reach the API without signing in. A service that is not wired yet still
    answers true, so the editor shows its gate rather than opening onto a login it cannot
    complete.
    """
    if svc is None:
        return {"login_required": True, "providers": []}
    return {"login_required": svc.requires_login, "providers": svc.providers}


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
    _set_session_cookie(response, token, svc.session_ttl_seconds)
    return response


def get_authenticated_user(request: Request, svc: Any = Depends(get_auth_service)) -> str:
    """Resolve the caller from the session cookie, or answer 401.

    Authentication only. The auth router's own routes use this, so that a caller who
    must change their password can still reach the routes that let them do that.
    Every other gated route goes through ``get_current_user``, which adds the
    must-change refusal on top.
    """
    if svc is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    token = request.cookies.get(_SESSION_COOKIE, "")
    user_id: str | None = svc.authenticate_cookie(token)
    if user_id is None or svc.resolve_session(user_id) is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user_id


def get_current_user(
    user_id: str = Depends(get_authenticated_user),
    svc: Any = Depends(get_auth_service),
) -> str:
    """Resolve the caller, refusing one who must change their password first.

    A login on a temporary password mints a real session, so without this the gate
    would let that session reach every manuscript route and the temporary password
    would keep working indefinitely. A flag shown but not enforced is not a control.
    It lives here because this is the dependency the manuscript routers are all
    registered with, so one place covers every route rather than each router having
    to remember. See ``README_auth.md`` §7.
    """
    if svc is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    if svc.requires_password_change(user_id):
        raise HTTPException(status_code=403, detail="password_change_required")
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
    user_id: str = Depends(get_authenticated_user),
    svc: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    """The signed-in caller's profile, and whether a password change is pending.

    Reachable while a change is pending, because the editor needs both answers to
    render the change-password screen at all. It reads only the account row, so it
    is not a way to the data: every route that serves a manuscript is still closed.
    """
    profile = svc.get_user(user_id)
    if profile is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return {
        "user": {
            "id": profile["id"],
            "username": profile["username"],
            # A provider account may have no address, and the store keeps that as
            # NULL so the unique email constraint does not collide two of them. The
            # wire format stays a plain string, which is what the editor's
            # UserProfile declares, so the empty string is substituted here.
            "email": profile["email"] or "",
            "display_name": profile["display_name"],
            "avatar_url": profile["avatar_url"],
        },
        "password_change_required": svc.requires_password_change(user_id),
    }


def _profile_for(user_id: str, svc: Any) -> dict[str, Any]:
    """The profile block a password sign-in returns alongside its cookie."""
    profile = svc.get_user(user_id)
    if profile is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return {
        "id": profile["id"],
        "username": profile["username"],
        "email": profile["email"] or "",
        "display_name": profile["display_name"],
        "avatar_url": profile["avatar_url"],
    }


@router.post("/api/auth/login/password")
async def auth_login_password(
    body: PasswordLoginRequest,
    request: Request,
    response: Response,
    svc: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    """Sign in with a username and password, and set the session cookie.

    The Argon2id verification runs in the threadpool. It is deliberately
    expensive — that is what makes a stolen hash costly to crack — so calling it on
    the event loop would stall every other request for the ~80ms it takes.
    """
    if svc is None:
        raise HTTPException(status_code=503, detail="backend_not_ready")
    try:
        user_id = await run_in_threadpool(
            svc.login_with_password,
            body.username,
            body.password,
            client_ip=_caller_ip(request),
        )
    except RateLimitedError as exc:
        # 429 with the standard header, so a client can back off without parsing
        # the body. The retry window is measured from the last failure, so waiting
        # this long is enough to be let through.
        raise HTTPException(
            status_code=429,
            detail="too_many_attempts",
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        ) from exc
    except LoginFailedError as exc:
        raise HTTPException(status_code=401, detail="invalid_username_or_password") from exc
    token = svc.session_cookie(user_id)
    _set_session_cookie(response, token, svc.session_ttl_seconds)
    return {
        "user": _profile_for(user_id, svc),
        "password_change_required": svc.requires_password_change(user_id),
    }


@router.post("/api/auth/change-password")
async def auth_change_password(
    body: ChangePasswordRequest,
    user_id: str = Depends(get_authenticated_user),
    svc: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    """Replace the caller's password, having first proved the one in force.

    ``current_password`` is required even though the session already names the
    account: on a temporary password — which is exactly the case this route exists
    to serve — the session proves nothing the account holder chose.

    A successful change ends the session it arrived on. Setting the password stamps
    ``credentials_changed_at``, and ``resolve_session`` refuses any session older
    than that stamp, so the cookie this request carried stops working. The response
    says so, and the editor presents the sign-in gate again.
    """
    if svc is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    try:
        await run_in_threadpool(svc.change_password, user_id, body.current_password, body.new_password)
    except LoginFailedError as exc:
        raise HTTPException(status_code=401, detail="invalid_username_or_password") from exc
    except PasswordUnchangedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PasswordPolicyError as exc:
        # The policy messages describe the rule and never quote the value, so this
        # is safe to show the person who is choosing the password.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "signed_out": True}


@router.post("/api/auth/logout")
def auth_logout(
    response: Response,
    user_id: str = Depends(get_authenticated_user),
    svc: Any = Depends(get_auth_service),
) -> dict[str, str]:
    """End the caller's session and clear its cookie.

    Reachable while a password change is pending: refusing it would trap a user who
    signed in on someone else's temporary password, with no way back to the gate.
    """
    if svc is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    svc.end_session(user_id)
    response.delete_cookie(_SESSION_COOKIE, path="/api")
    return {"status": "ok"}
