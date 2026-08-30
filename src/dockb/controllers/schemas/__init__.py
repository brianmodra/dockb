"""Pydantic wire-format schemas for the DockB API."""

from dockb.controllers.schemas.chapters import (
    ChapterRelations,
    CreateChapterRequest,
    UpdateChapterRequest,
)
from dockb.controllers.schemas.common import ErrorResponse, MutationResponse, Status
from dockb.controllers.schemas.documents import (
    CreateDocumentRequest,
    DocumentAttrs,
    DocumentResponse,
    DocumentSummary,
    UpdateDocumentRequest,
)
from dockb.controllers.schemas.history import HistoryResponse, RestoreRequest, Snapshot
from dockb.controllers.schemas.nodes import (
    ChapterAttrs,
    ChapterNode,
    ChapterSummary,
    ParagraphAttrs,
    ParagraphNode,
    SentenceAttrs,
    SentenceNode,
    TextNode,
)
from dockb.controllers.schemas.notifications import (
    NotificationPayload,
    NotificationsResponse,
    ParagraphSplitNotification,
    SentenceSplitNotification,
)
from dockb.controllers.schemas.paragraphs import (
    CreateParagraphRequest,
    ParagraphRelations,
    UpdateParagraphRelations,
    UpdateParagraphRequest,
)
from dockb.controllers.schemas.sentences import (
    CreateSentenceRequest,
    SentenceRelations,
    UpdateSentenceRelations,
    UpdateSentenceRequest,
)

__all__ = [
    # common
    "Status",
    "MutationResponse",
    "ErrorResponse",
    # nodes
    "TextNode",
    "SentenceAttrs",
    "SentenceNode",
    "ParagraphAttrs",
    "ParagraphNode",
    "ChapterAttrs",
    "ChapterNode",
    "ChapterSummary",
    # documents
    "DocumentAttrs",
    "DocumentResponse",
    "DocumentSummary",
    "CreateDocumentRequest",
    "UpdateDocumentRequest",
    # chapters
    "ChapterRelations",
    "CreateChapterRequest",
    "UpdateChapterRequest",
    # paragraphs
    "ParagraphRelations",
    "UpdateParagraphRelations",
    "CreateParagraphRequest",
    "UpdateParagraphRequest",
    # sentences
    "SentenceRelations",
    "UpdateSentenceRelations",
    "CreateSentenceRequest",
    "UpdateSentenceRequest",
    # notifications
    "NotificationPayload",
    "SentenceSplitNotification",
    "ParagraphSplitNotification",
    "NotificationsResponse",
    # history
    "Snapshot",
    "HistoryResponse",
    "RestoreRequest",
]
