"""The narrative perspectives a document can be written from.

A document stores the chosen **code**; the editor shows the matching label. An
empty string means no perspective has been chosen, so the stored value is either
``""`` or one of the codes below.
"""

from __future__ import annotations

NARRATIVE_PERSPECTIVES: tuple[tuple[str, str], ...] = (
    ("first_person", "First Person"),
    ("first_person_present", "First Person Present"),
    ("first_person_past", "First Person Past"),
    ("first_person_peripheral", "First Person Peripheral"),
    ("first_person_unreliable", "First Person Unreliable"),
    ("first_person_plural", "First Person Plural"),
    ("second_person", "Second Person"),
    ("second_person_present", "Second Person Present"),
    ("second_person_past", "Second Person Past"),
    ("third_person_limited", "Third Person Limited"),
    ("third_person_limited_present", "Third Person Limited Present"),
    ("third_person_limited_past", "Third Person Limited Past"),
    ("third_person_limited_multiple", "Third Person Limited Multiple"),
    ("third_person_objective", "Third Person Objective"),
    ("third_person_omniscient", "Third Person Omniscient"),
    ("third_person_omniscient_present", "Third Person Omniscient Present"),
    ("third_person_omniscient_past", "Third Person Omniscient Past"),
    ("third_person_cinematic", "Third Person Cinematic"),
    ("third_person_head_hopping", "Third Person Head Hopping"),
    ("epistolary", "Epistolary"),
)

NARRATIVE_PERSPECTIVE_CODES = frozenset(code for code, _label in NARRATIVE_PERSPECTIVES)


def validate_narrative_perspective(value: str) -> str:
    """Return *value* when it is empty or a known code, else raise ValueError."""
    if value == "" or value in NARRATIVE_PERSPECTIVE_CODES:
        return value
    raise ValueError(f"Unknown narrative perspective: {value}")
