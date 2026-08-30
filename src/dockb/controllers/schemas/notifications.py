"""Async notification payload schemas.

NLP processing (sentence splitting, paragraph splitting) runs asynchronously
after a POST or PUT returns.  When processing completes, the results are
stored in the session context and delivered to the client via piggy-back or
``GET /api/notifications`` poll.

Notification child nodes use the same ProseMirror format as GET responses.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from dockb.controllers.schemas.nodes import ParagraphNode, SentenceNode


class SentenceSplitNotification(BaseModel):
    """spaCy detected multiple sentences in a sentence's text."""

    type: Literal["sentence_split"] = "sentence_split"
    paragraph_id: str
    changed_sentences: list[SentenceNode]


class ParagraphSplitNotification(BaseModel):
    """spaCy detected paragraph boundaries in combined text (bulk import only)."""

    type: Literal["paragraph_split"] = "paragraph_split"
    chapter_id: str
    changed_paragraphs: list[ParagraphNode]


NotificationPayload = Annotated[
    SentenceSplitNotification | ParagraphSplitNotification,
    "Discriminated union of notification types",
]


class NotificationsResponse(BaseModel):
    """GET /api/notifications response."""

    notifications: list[NotificationPayload]
