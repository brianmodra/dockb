"""Move paragraph layouts from the legacy ``quote_type`` property to the structured pair.

Run with ``dockb migrate-layout [--dry-run] [--document-id ID]``. Before this
release a Paragraph carried one ``quote_type`` string: empty for normal prose,
``reading`` or ``writing`` for a quote. The current model stores that as
``layout_kind`` plus ``layout_variant``, so this command copies the old value into
the pair and removes the old property. It is idempotent: a second run finds no
paragraphs carrying ``quote_type`` and changes nothing.

``--dry-run`` reports what would change without writing. ``--document-id`` limits
the scan to one document. A value outside the old vocabulary is refused as a
single ``error:`` line and nothing is written, so a hand-edited graph cannot be
silently flattened to normal prose.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from dotenv import load_dotenv

from dockb.cli.startup import MissingConfigurationError, neo4j_settings
from dockb.infrastructure.neo4j.session_factory import SessionFactory

_SELECT_CYPHER = """
MATCH (p:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(d:Document)
WHERE p.quote_type IS NOT NULL
  AND ($document_id IS NULL OR d.id = $document_id)
RETURN p.id AS paragraph_id, p.quote_type AS quote_type
ORDER BY p.id
"""

_UPDATE_CYPHER = """
UNWIND $rows AS row
MATCH (p:Paragraph {id: row.paragraph_id})
SET p.layout_kind = row.layout_kind, p.layout_variant = row.layout_variant
REMOVE p.quote_type
"""

_QUOTE_VARIANTS = {"reading", "writing"}


class InvalidQuoteTypeError(Exception):
    """A stored ``quote_type`` is outside the values the old model documented."""


def layout_for(paragraph_id: str, quote_type: str) -> tuple[str, str]:
    """Return the structured layout equivalent to one legacy quote type."""
    if quote_type == "":
        return "normal", ""
    if quote_type in _QUOTE_VARIANTS:
        return "quoted", quote_type
    raise InvalidQuoteTypeError(f"paragraph {paragraph_id!r} has quote_type {quote_type!r}; expected '', 'reading', or 'writing'")


def planned_rows(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Turn selected graph records into update rows, refusing an unknown quote type."""
    rows: list[dict[str, str]] = []
    for record in records:
        paragraph_id = str(record["paragraph_id"])
        kind, variant = layout_for(paragraph_id, str(record.get("quote_type") or ""))
        rows.append({"paragraph_id": paragraph_id, "layout_kind": kind, "layout_variant": variant})
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dockb migrate-layout", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    parser.add_argument("--document-id", default=None, help="migrate only the paragraphs of this document")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Migrate every paragraph's legacy ``quote_type`` into the structured layout."""
    args = _build_parser().parse_args(argv)
    load_dotenv()
    try:
        settings = neo4j_settings()
    except MissingConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    session_factory = SessionFactory(
        uri=settings["NEO4J_URL"],
        user=settings["NEO4J_USER"],
        password=settings["NEO4J_PASSWORD"],
    )
    try:
        with session_factory.session() as session:
            records = [dict(record) for record in session.run(_SELECT_CYPHER, {"document_id": args.document_id})]
            try:
                rows = planned_rows(records)
            except InvalidQuoteTypeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            if not args.dry_run and rows:
                session.run(_UPDATE_CYPHER, {"rows": rows})
    finally:
        session_factory.close()

    verb = "would migrate" if args.dry_run else "migrated"
    print(f"{verb} {len(rows)} paragraph(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
