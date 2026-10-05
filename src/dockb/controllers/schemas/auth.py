"""Auth request / response schemas for the password flow.

The passwords are plain strings, not ``SecretStr``: the value is needed verbatim to
HMAC and hash it, and pydantic's wrapper would only have to be unwrapped again.
They are request bodies and are never logged, which is what keeps them out of
the debug output. See ``README_auth.md`` §7.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PasswordLoginRequest(BaseModel):
    """``POST /api/auth/login/password`` request body."""

    username: str = Field(min_length=1, description="Account username; matched case-insensitively")
    password: str = Field(min_length=1, description="The account's password")


class PasswordLoginResponse(BaseModel):
    """``POST /api/auth/login/password`` response, alongside the session cookie.

    ``password_change_required`` is here so the editor knows to show the
    change-password screen without having to make a request that is about to be
    refused.
    """

    user: dict[str, str]
    password_change_required: bool


class ChangePasswordRequest(BaseModel):
    """``POST /api/auth/change-password`` request body.

    ``current_password`` is required rather than optional: the session already
    proves which account is calling, but on a temporary password that proves
    nothing the account holder did not choose. See ``README_auth.md`` §7.
    """

    current_password: str = Field(min_length=1, description="The password now in force")
    new_password: str = Field(min_length=1, description="Its replacement")


class ChangePasswordResponse(BaseModel):
    """``POST /api/auth/change-password`` response.

    ``signed_out`` is always true. Setting the password stamps
    ``credentials_changed_at``, which refuses every session older than the stamp,
    so the session this request arrived on no longer exists. Saying so lets the
    editor present the sign-in gate instead of a page that will 401.
    """

    status: str = "ok"
    signed_out: bool = True
