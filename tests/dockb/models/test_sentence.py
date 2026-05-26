"""Tests for Sentence text-editing operations and tokenization."""

import pytest
import spacy

from dockb.exceptions import EditTextRangeError
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.sync_sentence_reconstructor import SyncSentenceReconstructor


@pytest.mark.parametrize(
    "operations, expected_text",
    [
        pytest.param([("append", "Hello World!")], "Hello World!", id="creates_text"),
        pytest.param(
            [("append", "Hello"), ("append", " World!")],
            "Hello World!",
            id="appends_text",
        ),
    ],
)
def test_apply_text_creates_or_appends_and_invalidates_semantics(sentence, operations, expected_text):
    for op, value in operations:
        if op == "append":
            sentence.apply_append_text(value)
    assert sentence.text == expected_text
    assert sentence.dirty


@pytest.mark.parametrize(
    "start, end, replacement, expected_text",
    [
        pytest.param(6, 10, "Sir", "Hello Sir!", id="replace_word"),
        pytest.param(11, 11, ".", "Hello World.", id="replace_single_char"),
        pytest.param(5, 10, "", "Hello!", id="empty_replacement_removes_text"),
    ],
)
def test_edit_text_replaces_text_and_invalidates_semantics(sentence, start, end, replacement, expected_text):
    sentence.apply_append_text("Hello World!")
    sentence.dirty = False
    sentence.apply_edit_text(start, end, replacement)
    assert sentence.text == expected_text
    assert sentence.dirty


@pytest.mark.parametrize(
    "start, end",
    [
        pytest.param(2, 1, id="end_before_start"),
        pytest.param(14, 14, id="start_out_of_range"),
        pytest.param(1, 15, id="end_out_of_range"),
        pytest.param(-1, 5, id="start_negative"),
        pytest.param(1, -1, id="end_negative"),
    ],
)
def test_edit_text_throws_for_invalid_ranges(sentence, start, end):
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(start, end, "this won't work")


def test_edit_text_throws_when_no_existing_text(sentence):
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(0, 0, "this won't work")


@pytest.mark.parametrize(
    "pos, insertion, expected_text",
    [
        pytest.param(0, "Hello ", "Hello World!", id="beginning"),
        pytest.param(5, " World", "Hello World!", id="middle"),
        pytest.param(5, " World!", "Hello World!", id="end"),
    ],
)
def test_insert_text_and_invalidates_semantics(sentence, pos, insertion, expected_text):
    if pos == 0 and insertion == "Hello ":
        sentence.apply_append_text("World!")
    elif pos == 5 and insertion == " World":
        sentence.apply_append_text("Hello!")
    else:
        sentence.apply_append_text("Hello")
    sentence.dirty = False
    sentence.apply_insert_text(pos, insertion)
    assert sentence.text == expected_text
    assert sentence.dirty


def test_insert_text_into_empty_sentence_at_zero(sentence):
    sentence.apply_insert_text(0, "Hello World!")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


@pytest.mark.parametrize(
    "pos, existing_text",
    [
        pytest.param(-1, "Hello World!", id="negative_pos"),
        pytest.param(14, "Hello World!", id="pos_out_of_range"),
        pytest.param(1, "", id="pos_out_of_range_with_no_text"),
    ],
)
def test_insert_text_throws_for_invalid_positions(sentence, pos, existing_text):
    if existing_text:
        sentence.apply_append_text(existing_text)
    with pytest.raises(EditTextRangeError):
        sentence.apply_insert_text(pos, "this won't work")


@pytest.mark.parametrize(
    "setup_text, pos, insertion",
    [
        pytest.param("Hello World!", 5, "", id="into_existing_text"),
        pytest.param("", 0, "", id="into_empty_sentence"),
    ],
)
def test_insert_text_with_empty_insertion_does_nothing(sentence, setup_text, pos, insertion):
    if setup_text:
        sentence.apply_append_text(setup_text)
    sentence.dirty = False
    sentence.apply_insert_text(pos, insertion)
    assert sentence.text == setup_text
    assert not sentence.dirty


@pytest.mark.parametrize(
    "existing_text",
    [
        pytest.param("", id="no_existing_text"),
        pytest.param("Hello", id="with_existing_text"),
    ],
)
def test_append_text_with_empty_string_does_nothing(sentence, existing_text):
    if existing_text:
        sentence.apply_append_text(existing_text)
        sentence.dirty = False
    sentence.apply_append_text("")
    assert sentence.text == existing_text
    assert not sentence.dirty


def test_each_sentence_has_unique_id():
    s1 = Sentence()
    s2 = Sentence()
    assert s1.id != s2.id
    assert isinstance(s1.id, str)


def test_sentence_can_tokenise():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    sentence_reconstructor = SyncSentenceReconstructor(cache)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat in the caf\u00e9 looking at the dog \U0001f61c.")
    sentence_reconstructor.run(sentence)
    expected = [
        Token(text="The", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="cat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="cat", pos=POS.NOUN),
        Token(text="sat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="sit", pos=POS.VERB),
        Token(text="on", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="on", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="mat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="mat", pos=POS.NOUN),
        Token(text="in", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="in", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(
            text="caf\u00e9",
            type=Type.WORD,
            trailing_ws=" ",
            is_digit=False,
            like_num=False,
            is_alpha=True,
            lemma="caf\u00e9",
            pos=POS.NOUN,
        ),
        Token(text="looking", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="look", pos=POS.VERB),
        Token(text="at", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="at", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="dog", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="dog", pos=POS.NOUN),
        Token(text="\U0001f61c", type=Type.EXTENDED, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma="", pos=POS._),
        Token(text=".", type=Type.PUNCTUATION, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma=".", pos=POS.PUNCT),
    ]
    print(sentence.tokens)
    assert len(sentence.tokens) == len(expected)
    for actual, exp in zip(sentence.tokens, expected, strict=True):
        assert actual.text == exp.text
        assert actual.type == exp.type
        assert actual.trailing_ws == exp.trailing_ws
        assert actual.is_digit == exp.is_digit
        assert actual.like_num == exp.like_num
        assert actual.is_alpha == exp.is_alpha
        assert actual.lemma == exp.lemma
        assert actual.pos == exp.pos


def test_clear_semantics_removes_tokens(sentence):
    sentence.tokens.append(Token(text="Hello"))
    sentence.tokens.append(Token(text="World", trailing_ws="!"))

    sentence.clear_semantics()

    assert len(sentence.tokens) == 0
