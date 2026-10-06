"""Import routes — POST /api/import.

An upload is a document directory sent as multipart parts whose names are paths
relative to the document folder. The server stages them in a temporary
directory and runs the same directory walker the shell command uses, so a
document can be brought into the graph without the caller naming a path the
server can read.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from dockb.controllers.auth import get_auth_service, get_current_user
from dockb.controllers.schemas.imports import ImportResponse, ImportSummaryWire
from dockb.exceptions import ChapterMismatchError, DocumentFormatError
from dockb.uploads import UploadRejectedError, UploadTooLargeError

router = APIRouter(prefix="/api", tags=["import"])

_import_service: Any = None


def get_import_service() -> Any:
    return _import_service


def set_import_service(service: Any) -> None:
    global _import_service  # noqa: PLW0603
    _import_service = service


@router.post("/import")
async def import_document(
    files: list[UploadFile] = File(..., description="the document directory's files, named by their path"),
    single_newline_paragraphs: bool = Form(False),
    svc: Any = Depends(get_import_service),
    owner: str = Depends(get_current_user),
    auth: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    if svc is None:
        raise HTTPException(status_code=503, detail="import_service_unavailable")
    # The account owns the imported document; the username is what the document's own
    # metadata records as its author, and a username is mutable provider data that a
    # reader of the manuscript sees. Keying ownership by it would move the document's
    # directory the day the account was renamed.
    account = auth.get_user(owner) if auth is not None else None
    if account is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    user_name = str(account["username"])
    try:
        summaries = await svc.import_parts(
            files,
            user_name,
            owner=owner,
            single_newline_paragraphs=single_newline_paragraphs,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UploadRejectedError as exc:
        # An unsafe or incoherent upload is the caller's document being wrong.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentFormatError as exc:
        # A document directory the walker cannot read, and a chapter whose
        # front matter names a chapter that is not this document's, are both
        # the caller's document being wrong. Each is a named type rather than
        # a bare ValueError so a bug of ours is not reported as a bad document.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ChapterMismatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImportResponse(imports=[ImportSummaryWire.from_summary(s) for s in summaries]).model_dump()
