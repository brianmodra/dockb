"""Proofreading routes — POST /api/check.

One paragraph in, the diagnostics for it out. The route is interactive-only:
nothing is written, and the engine never enters the save path. The signed-in
account supplies the document's glossary and character names (see
``controllers/glossary.py``); the text itself is the request's.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_auth_service, get_current_user, get_owner
from dockb.controllers.glossary import get_glossary_service
from dockb.controllers.schemas.proofreading import (
    CheckRequest,
    CheckResponse,
    LanguageOption,
    LanguagesResponse,
    SetLanguageRequest,
)
from dockb.controllers.schemas.proofreading import (
    Diagnostic as DiagnosticWire,
)
from dockb.controllers.schemas.proofreading import (
    QuotePair as QuotePairWire,
)
from dockb.exceptions import DocumentNotFoundError
from dockb.services.proofreading import (
    ProofreadingDisabledError,
    ProofreadingError,
    ProofreadingUnavailableError,
    TextTooLongError,
    UnsupportedLanguageError,
)

router = APIRouter(prefix="/api", tags=["proofreading"])

_proofreading_service: Any = None


def get_proofreading_service() -> Any:
    return _proofreading_service


def set_proofreading_service(service: Any) -> None:
    global _proofreading_service  # noqa: PLW0603
    _proofreading_service = service


def _supported_codes(svc: Any) -> set[str]:
    """Return the language codes *svc* accepts."""
    return {code for code, _label in svc.supported_languages()}


def _language_for(auth: Any, user: str, svc: Any) -> str:
    """Return the language to check in when the request names none.

    The writer's stored choice wins when it is still supported; otherwise the
    service's configured default, so a preference left behind by a removed
    language cannot make every check fail.
    """
    stored = auth.get_proofreading_language(user) if auth is not None else None
    return stored if stored in _supported_codes(svc) else cast("str", svc.default_language)


def _languages_response(svc: Any, default: str) -> dict[str, Any]:
    return LanguagesResponse(
        languages=[LanguageOption(code=code, label=label) for code, label in svc.supported_languages()],
        default=default,
    ).model_dump()


@router.get("/check/languages")
def languages(
    svc: Any = Depends(get_proofreading_service),
    user: str = Depends(get_current_user),
    auth: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    if svc is None:
        raise HTTPException(status_code=503, detail="proofreading_unavailable")
    return _languages_response(svc, _language_for(auth, user, svc))


@router.put("/check/language")
def set_language(
    body: SetLanguageRequest,
    svc: Any = Depends(get_proofreading_service),
    user: str = Depends(get_current_user),
    auth: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    """Persist the writer's chosen proofreading language for their account."""
    if svc is None:
        raise HTTPException(status_code=503, detail="proofreading_unavailable")
    if body.language not in _supported_codes(svc):
        raise HTTPException(status_code=422, detail=f"unsupported language: {body.language}")
    if auth is not None:
        auth.set_proofreading_language(user, body.language)
    return _languages_response(svc, body.language)


@router.post("/check")
def check(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    body: CheckRequest,
    svc: Any = Depends(get_proofreading_service),
    glossary: Any = Depends(get_glossary_service),
    owner: str = Depends(get_owner),
    user: str = Depends(get_current_user),
    auth: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    if svc is None:
        raise HTTPException(status_code=503, detail="proofreading_unavailable")
    accepted_words: tuple[str, ...] = ()
    if glossary is not None:
        try:
            accepted_words = glossary.effective_words(
                body.document_id,
                owner=owner,
                username=user,
            )
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="document_not_found") from exc
    focus_start = body.focus.start if body.focus is not None else None
    focus_end = body.focus.end if body.focus is not None else None
    language = body.language or _language_for(auth, user, svc)
    try:
        diagnostics = svc.check(
            body.text,
            language,
            focus_start=focus_start,
            focus_end=focus_end,
            accepted_words=accepted_words,
        )
    except ProofreadingDisabledError as exc:
        raise HTTPException(status_code=503, detail=f"proofreading_disabled: {exc}") from exc
    except (UnsupportedLanguageError, TextTooLongError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProofreadingUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"proofreading_unavailable: {exc}") from exc
    except ProofreadingError as exc:
        raise HTTPException(status_code=502, detail=f"proofreading_failed: {exc}") from exc
    return CheckResponse(
        language=language,
        diagnostics=[
            DiagnosticWire(
                rule_id=diagnostic.rule_id,
                category=diagnostic.category,
                severity=diagnostic.severity,
                message=diagnostic.message,
                start=diagnostic.start,
                end=diagnostic.end,
                replacements=list(diagnostic.replacements),
                pair=(
                    QuotePairWire(
                        replacement=diagnostic.pair.replacement,
                        partner_start=diagnostic.pair.partner_start,
                        partner_end=diagnostic.pair.partner_end,
                        partner_replacement=diagnostic.pair.partner_replacement,
                    )
                    if diagnostic.pair is not None
                    else None
                ),
                in_focus=diagnostic.in_focus,
            )
            for diagnostic in diagnostics
        ],
    ).model_dump()
