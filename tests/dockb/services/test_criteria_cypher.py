"""The criteria-tree → Cypher compiler (services/criteria_cypher.py)."""

from __future__ import annotations

from dockb.services.criteria_cypher import compile_criteria


def _resolve(reference: str) -> tuple[str, list[str]] | None:
    if reference == "Karakas":
        return ("c1", ["Karakas", "Karakas Benhur"])
    return None


def test_a_word_leaf_is_a_whole_word_regex_parameter() -> None:
    where, params = compile_criteria({"type": "word", "word": "murder"}, _resolve)
    assert where == "(text =~ $p0)"
    assert params == {"p0": "(?isuU).*\\bmurder\\b.*"}


def test_a_word_leaf_escapes_regex_metacharacters() -> None:
    where, params = compile_criteria({"type": "word", "word": "C.E.O."}, _resolve)
    assert params == {"p0": "(?isuU).*\\bC\\.E\\.O\\.\\b.*"}


def test_a_text_leaf_is_a_caseless_substring() -> None:
    where, params = compile_criteria({"type": "text", "text": "Was Discovered"}, _resolve)
    assert where == "(toLower(text) CONTAINS $p0)"
    assert params == {"p0": "was discovered"}


def test_a_character_leaf_branches_between_the_cache_and_inline_names() -> None:
    where, params = compile_criteria({"type": "character", "character": "Karakas"}, _resolve)
    assert where == ("((checked IS NOT NULL AND NOT hasStale AND $p0 IN valid) " "OR (any(n IN $p1 WHERE text =~ n)))")
    assert params == {
        "p0": "c1",
        # re.escape quotes the space; Java's regex engine reads `\ ` as a literal space
        "p1": ["(?isuU).*\\bKarakas\\b.*", "(?isuU).*\\bKarakas\\ Benhur\\b.*"],
    }


def test_an_unresolved_character_matches_nothing() -> None:
    where, params = compile_criteria({"type": "character", "character": "Nobody"}, _resolve)
    assert where == "false"
    assert not params


def test_an_and_group_demands_every_child() -> None:
    where, _ = compile_criteria(
        {
            "type": "criteria",
            "op": "and",
            "criteria": [
                {"type": "word", "word": "murder"},
                {"type": "text", "text": "scene"},
            ],
        },
        _resolve,
    )
    assert where == "((text =~ $p0) AND (toLower(text) CONTAINS $p1))"


def test_an_or_group_accepts_any_child() -> None:
    _, params = compile_criteria(
        {
            "type": "criteria",
            "op": "or",
            "criteria": [
                {"type": "word", "word": "murder"},
                {"type": "word", "word": "discovered"},
            ],
        },
        _resolve,
    )
    assert list(params.values()) == ["(?isuU).*\\bmurder\\b.*", "(?isuU).*\\bdiscovered\\b.*"]


def test_groups_nest() -> None:
    where, _ = compile_criteria(
        {
            "type": "criteria",
            "op": "and",
            "criteria": [
                {"type": "character", "character": "Karakas"},
                {
                    "type": "criteria",
                    "op": "or",
                    "criteria": [
                        {"type": "word", "word": "murder"},
                        {"type": "text", "text": "killed"},
                    ],
                },
            ],
        },
        _resolve,
    )
    assert where == (
        "(((checked IS NOT NULL AND NOT hasStale AND $p0 IN valid) "
        "OR (any(n IN $p1 WHERE text =~ n))) "
        "AND ((text =~ $p2) OR (toLower(text) CONTAINS $p3)))"
    )


def test_an_empty_and_group_matches_everything_and_an_empty_or_group_nothing() -> None:
    where, _ = compile_criteria({"type": "criteria", "op": "and", "criteria": []}, _resolve)
    assert where == "true"
    where, _ = compile_criteria({"type": "criteria", "op": "or", "criteria": []}, _resolve)
    assert where == "false"


def test_an_unknown_leaf_matches_nothing() -> None:
    where, params = compile_criteria({"words": ["murdered"]}, _resolve)
    assert where == "false"
    assert not params
