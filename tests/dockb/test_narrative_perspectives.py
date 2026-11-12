"""Tests for the fixed narrative-perspective vocabulary."""

import pytest

from dockb.narrative_perspectives import (
    NARRATIVE_PERSPECTIVE_CODES,
    NARRATIVE_PERSPECTIVES,
    validate_narrative_perspective,
)


def test_has_twenty_perspectives() -> None:
    assert len(NARRATIVE_PERSPECTIVES) == 20


def test_codes_are_unique() -> None:
    codes = [code for code, _label in NARRATIVE_PERSPECTIVES]
    assert len(codes) == len(set(codes))


def test_labels_are_non_blank() -> None:
    assert all(label.strip() for _code, label in NARRATIVE_PERSPECTIVES)


def test_codes_keep_the_approved_order() -> None:
    assert [code for code, _label in NARRATIVE_PERSPECTIVES] == [
        "first_person",
        "first_person_present",
        "first_person_past",
        "first_person_peripheral",
        "first_person_unreliable",
        "first_person_plural",
        "second_person",
        "second_person_present",
        "second_person_past",
        "third_person_limited",
        "third_person_limited_present",
        "third_person_limited_past",
        "third_person_limited_multiple",
        "third_person_objective",
        "third_person_omniscient",
        "third_person_omniscient_present",
        "third_person_omniscient_past",
        "third_person_cinematic",
        "third_person_head_hopping",
        "epistolary",
    ]


def test_code_set_matches_the_pairs() -> None:
    assert NARRATIVE_PERSPECTIVE_CODES == {code for code, _label in NARRATIVE_PERSPECTIVES}


@pytest.mark.parametrize(("code", "label"), NARRATIVE_PERSPECTIVES)
def test_known_code_is_accepted(code: str, label: str) -> None:
    assert validate_narrative_perspective(code) == code
    assert label


def test_empty_string_means_no_perspective() -> None:
    assert validate_narrative_perspective("") == ""


@pytest.mark.parametrize("value", ["unknown", "First Person", "first-person"])
def test_unknown_code_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="(?i)narrative perspective"):
        validate_narrative_perspective(value)
