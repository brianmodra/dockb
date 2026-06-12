"""Tests for Sentence model."""

import logging

import pytest
import spacy

from dockb.models.base import DataState
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type
from dockb.models.utils.dockb_collection import InsertionMode
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.sync_reconstructor import SyncReconstructor


def test_each_sentence_has_unique_id():
    s1 = Sentence()
    s2 = Sentence()
    assert s1.id != s2.id
    assert isinstance(s1.id, str)


def test_set_text_sets_dirty(sentence):
    sentence.set_text("Hello")
    assert sentence.text == "Hello"
    assert sentence.dirty


def test_sentence_can_tokenise():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat in the caf\u00e9 looking at the dog \U0001f61c.")
    reconstructor.run(sentence)
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
    sentence.tokens.append(Token(text="World"))
    sentence.tokens.append(Token(text="!"))

    sentence.clear_semantics()

    assert len(sentence.tokens) == 0


def test_delete_child_removes_a_token_from_a_sentence(sentence):
    token = Token(text="!")
    sentence.tokens.append(Token(text="Hello", trailing_ws=" "))
    sentence.tokens.append(Token(text="World"))
    sentence.tokens.append(token)

    assert len(sentence.tokens) == 3

    assert sentence.delete_child(token.id)

    assert len(sentence.tokens) == 2
    assert not sentence.dirty
    assert sentence.get_text() == "Hello World"
    assert sentence.tokens[0].text == "Hello"
    assert sentence.tokens[1].text == "World"


def test_insert_child_last_appends_token(sentence):
    token_a = Token(text="Hello", trailing_ws=" ")
    token_b = Token(text="World")
    sentence.tokens.append(token_a)
    sentence.tokens.append(token_b)
    sentence.insert_child(Token(text="!"), InsertionMode.LAST)

    assert len(sentence.tokens) == 3
    assert list(sentence.tokens)[0] is token_a
    assert list(sentence.tokens)[1] is token_b
    assert list(sentence.tokens)[2].text == "!"


def test_insert_child_first_prepends_token(sentence):
    token_a = Token(text="Hello", trailing_ws=" ")
    token_b = Token(text="World")
    sentence.tokens.append(token_a)
    sentence.tokens.append(token_b)
    first = Token(text="!")
    sentence.insert_child(first, InsertionMode.FIRST)

    assert len(sentence.tokens) == 3
    assert list(sentence.tokens)[0] is first
    assert list(sentence.tokens)[1] is token_a
    assert list(sentence.tokens)[2] is token_b


def test_insert_child_after_inserts_in_middle(sentence):
    token_a = Token(text="Hello", trailing_ws=" ")
    token_b = Token(text="World")
    sentence.tokens.append(token_a)
    sentence.tokens.append(token_b)
    middle = Token(text="there", trailing_ws=" ")
    sentence.insert_child(middle, InsertionMode.AFTER, token_a.id)

    assert len(sentence.tokens) == 3
    assert list(sentence.tokens)[0] is token_a
    assert list(sentence.tokens)[1] is middle
    assert list(sentence.tokens)[2] is token_b


def test_insert_child_sets_parent(sentence):
    token = Token(text="Hello")
    sentence.insert_child(token, InsertionMode.LAST)

    assert token.get_parent() is sentence


def test_insert_child_raises_type_error_for_wrong_type(sentence):
    not_token = Sentence()
    with pytest.raises(TypeError, match="Expected Token"):
        sentence.insert_child(not_token, InsertionMode.LAST)
    with pytest.raises(TypeError, match="Expected Token"):
        sentence.insert_child(Sentence(), InsertionMode.LAST)


def test_append_child_to_nothing_sentence_changes_state_to_new(sentence):
    token = Token(text="Hello")
    assert sentence.state == DataState._
    sentence.append_child(token)
    assert sentence.state == DataState.NEW


def test_append_child_to_new_sentence_does_not_change_state_to_changed(sentence):
    token = Token(text="Hello")
    # force it to NEW for the test
    sentence.state = DataState.NEW
    sentence.append_child(token)
    assert sentence.state == DataState.NEW


def test_append_child_to_changed_sentence_leaves_state_as_changed(sentence):
    token = Token(text="Hello")
    # force it to NEW for the test
    sentence.state = DataState.CHANGED
    sentence.append_child(token)
    assert sentence.state == DataState.CHANGED


def test_append_child_to_sync_sentence_changes_state_to_changed(sentence):
    token = Token(text="Hello")
    # force it to SYNC for the test
    sentence.state = DataState.SYNC
    sentence.append_child(token)
    assert sentence.state == DataState.CHANGED


def test_append_child_to_deleted_sentence_resurrects_it_and_changes_state_to_changed(sentence, caplog):
    # the logic here is that if it was DELETED, and then changed, well, it
    # must have been resurrected. But this could be a bug, so it must warn.
    caplog.set_level(logging.WARN)
    token = Token(text="Hello")
    # force it to DELETED for the test
    sentence.state = DataState.DELETED
    sentence.append_child(token)
    assert sentence.state == DataState.CHANGED
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert "changed" in caplog.records[0].message


def test_set_text_on_nothing_sentence_changes_state_to_new(sentence):
    assert sentence.state == DataState._
    sentence.set_text("Hello World")
    assert sentence.state == DataState.NEW


def test_set_text_on_new_sentence_leaves_states_as_new(sentence):
    sentence.set_text("Hello World")  # make it NEW
    sentence.set_text("Hello World!")  # change it
    assert sentence.state == DataState.NEW
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat.")
    reconstructor.run(sentence)
    assert sentence.state == DataState.NEW


def test_set_text_on_sync_sentence_changes_state_to_changed(sentence):
    sentence.state = DataState.SYNC
    sentence.set_text("Hello World")
    assert sentence.state == DataState.CHANGED
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    sentence = Sentence()
    reconstructor.run(sentence)
    sentence.state = DataState.SYNC  # reset it to SYNC and this time change the existing
    sentence.set_text("Hello World!")
    assert sentence.state == DataState.CHANGED
