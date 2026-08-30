"""Common envelope types for API responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


class Status(BaseModel):
    """Status block returned in mutation and error responses."""

    code: str = "ok"
    message: str = "success"


class MutationResponse(BaseModel):
    """Response envelope for POST / PUT / DELETE endpoints.

    Carries an optional list of async notifications (e.g. sentence splits)
    that were pending when the mutation completed.
    """

    status: Status = Field(default_factory=Status)
    notifications: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Response envelope for error conditions."""

    status: Status
