"""Paragraph layout attributes on the canonical paragraph span.

The canonical form writes ``data-layout-kind`` and ``data-layout-variant`` only
when the layout is not ``normal``. A file written before layouts existed carries
``data-quote-type`` instead; that is read for compatibility and never written.
"""

from __future__ import annotations

import html

from dockb.models.formatting import LAYOUT_KINDS, LAYOUT_VARIANTS, LayoutKind, LayoutVariant

LAYOUT_KIND_ATTR = "data-layout-kind"
LAYOUT_VARIANT_ATTR = "data-layout-variant"
LEGACY_QUOTE_ATTR = "data-quote-type"


def parse_layout(
    kind: str | None,
    variant: str | None,
    quote_type: str | None = None,
) -> tuple[LayoutKind, LayoutVariant]:
    """Return ``(layout_kind, layout_variant)`` from a paragraph span's attributes.

    The new attributes win. When neither is present, a legacy
    ``data-quote-type`` maps ``""`` to ``normal`` and ``reading``/``writing`` to
    ``quoted`` with that variant. A value outside the allowed sets is malformed
    markdown and raises ``ValueError``.
    """
    if kind is None and variant is None:
        legacy = quote_type or ""
        parsed_kind: str = "quoted" if legacy else "normal"
        parsed_variant: str = legacy
    else:
        parsed_kind = kind or "normal"
        parsed_variant = variant or ""

    if parsed_kind not in LAYOUT_KINDS:
        raise ValueError(f"'{parsed_kind}' is not a valid paragraph layout kind")
    if parsed_variant not in LAYOUT_VARIANTS:
        raise ValueError(f"'{parsed_variant}' is not a valid paragraph layout variant")
    return parsed_kind, parsed_variant


def render_layout_attributes(kind: LayoutKind, variant: LayoutVariant) -> str:
    """Return the span attributes for *kind*/*variant*; ``normal`` renders none."""
    if kind == "normal":
        return ""
    attributes = f' {LAYOUT_KIND_ATTR}="{html.escape(kind, quote=True)}"'
    if variant:
        attributes += f' {LAYOUT_VARIANT_ATTR}="{html.escape(variant, quote=True)}"'
    return attributes
