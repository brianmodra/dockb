"""Document mentions route — GET /api/documents/{document_id}/mentions.

The mention map is the cached verdicts the mention pipeline writes: for each
paragraph, the character chapters its valid verdicts name. The frontend reads it
to list the characters of the paragraph being edited. It is editor-facing, not a
manuscript mutation, so nothing here writes the graph, the file, or a snapshot.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_current_user, get_owner

router = APIRouter(prefix="/api/documents", tags=["mentions"])

_mentions_repo: Any = None


def get_mentions_repo() -> Any:
    return _mentions_repo


def set_mentions_repo(repo: Any) -> None:
    global _mentions_repo  # noqa: PLW0603
    _mentions_repo = repo


@router.get("/{document_id}/mentions")
def document_mentions(
    document_id: str,
    repo: Any = Depends(get_mentions_repo),
    owner: str = Depends(get_owner),
    _user: str = Depends(get_current_user),
) -> dict[str, Any]:
    if repo is None:
        raise HTTPException(status_code=503, detail="mentions_unavailable")
    return {"mentions": repo.document_mentions(document_id, owner)}
