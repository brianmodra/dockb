"""Convert wire-format ProseMirror nodes into in-memory model objects.

Tokens are server-only — the wire format carries ``TextNode`` content whose
text is extracted and set on the ``Sentence`` model (marking it dirty).
Tokenisation happens asynchronously via the job queue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dockb.models.sentence import Sentence

if TYPE_CHECKING:
    from dockb.controllers.schemas.nodes import SentenceNode, TextNode


def _extract_text(nodes: list[TextNode]) -> str:
    """Concatenate text from a list of ``TextNode`` objects."""
    return "".join(n.text for n in nodes)


def desugar_sentence(node: SentenceNode) -> Sentence:
    """Convert a ``SentenceNode`` wire-format node into a ``Sentence`` model.

    The sentence's text is set from the concatenated ``TextNode`` children
    and the model is marked dirty for async tokenisation.
    """
    text = _extract_text(node.content)
    assert node.attrs.id is not None  # noqa: S101 — required by wire contract
    sent = Sentence(id=node.attrs.id)
    sent.set_text(text)
    return sent


def desugar_sentences(nodes: list[SentenceNode]) -> list[Sentence]:
    """Convert a list of ``SentenceNode`` objects into ``Sentence`` models."""
    return [desugar_sentence(n) for n in nodes]


def extract_text_from_nodes(nodes: list[TextNode]) -> str:
    """Concatenate raw text from ``TextNode`` objects (public helper)."""
    return _extract_text(nodes)
