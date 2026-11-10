"""POST /api/check schemas — one paragraph in, diagnostics out."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FocusSpan(BaseModel):
    """The sentence the writer is editing, as offsets into the paragraph text."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class CheckRequest(BaseModel):
    """The paragraph to check and the sentence the writer is editing."""

    text: str = Field(min_length=1)
    language: str | None = None
    document_id: str | None = None
    paragraph_id: str | None = None
    focus: FocusSpan | None = None


class Diagnostic(BaseModel):
    """One finding, anchored to paragraph-relative offsets."""

    rule_id: str
    category: str
    severity: str
    message: str
    start: int
    end: int
    replacements: list[str] = Field(default_factory=list)
    in_focus: bool = False


class CheckResponse(BaseModel):
    """The diagnostics found in the requested paragraph."""

    language: str
    diagnostics: list[Diagnostic]


class LanguageOption(BaseModel):
    """One selectable proofreading language."""

    code: str
    label: str


class LanguagesResponse(BaseModel):
    """The proofreading languages the editor may choose from."""

    languages: list[LanguageOption]
