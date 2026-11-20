"""Tests for dialogue speaker attribution."""

from __future__ import annotations

from unittest.mock import MagicMock

from dockb.models.chapter import Chapter
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token
from dockb.services.dialogue import DialogueSpan
from dockb.services.speakers import UNRESOLVED_ID, SpeakerVerdict, find_speakers

_OWNER = "acct-1"
_DOC = "d-1"


def _token(text: str, pos: POS, *, lemma: str = "", trailing_ws: str = " ") -> Token:
    return Token(text=text, pos=pos, lemma=lemma or text.lower(), trailing_ws=trailing_ws)


def _sentence(sentence_id: str, *tokens: Token) -> Sentence:
    return Sentence(id=sentence_id, tokens=list(tokens))


def _span(
    sentence: Sentence,
    start_token: int,
    end_token: int,
    *,
    paragraph: int = 0,
    sentence_index: int = 0,
    group: int = 0,
    continues: bool = False,
) -> DialogueSpan:
    offsets: list[int] = []
    position = 0
    for token in sentence.tokens:
        offsets.append(position)
        position += len(token.text) + len(token.trailing_ws)
    return DialogueSpan(
        paragraph=paragraph,
        sentence=sentence_index,
        start=offsets[start_token],
        end=offsets[end_token],
        group=group,
        continues=continues,
    )


def _character(character_id: str, *, gender: str | None = None, name: str = "") -> Chapter:
    return Chapter(
        id=character_id,
        category="Character",
        title=name or character_id,
        first_name=name,
        gender=gender,  # type: ignore[arg-type]
    )


def _repo(names: dict[str, str] | None = None) -> MagicMock:
    repo = MagicMock()
    lookup = names or {}

    def find(_document_id: str, words: list[str], _owner: str) -> dict[str, str] | None:
        character_id = lookup.get(" ".join(word.lower() for word in words))
        return {"id": character_id, "title": character_id} if character_id else None

    repo.find_character_by_name.side_effect = find
    return repo


def _run(paragraphs, spans, characters, repo):
    return find_speakers(paragraphs, spans, characters, chapter_repo=repo, document_id=_DOC, owner=_OWNER)


def test_resolves_a_proper_name_after_the_dialogue() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token(",", POS.PUNCT, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("Mary", POS.PROPN),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )
    repo = _repo({"mary": "c1"})

    verdicts = _run([[sentence]], [_span(sentence, 1, 3)], [_character("c1", name="Mary")], repo)

    assert verdicts == [SpeakerVerdict("s1", 0, "Mary", "c1", "name", 1.0)]
    repo.find_character_by_name.assert_called_once_with(_DOC, ["mary"], _OWNER)


def test_resolves_a_proper_name_before_the_dialogue() -> None:
    sentence = _sentence(
        "s1",
        _token("Mary", POS.PROPN),
        _token("said", POS.VERB, lemma="say"),
        _token(",", POS.PUNCT),
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
        _token('"', POS.PUNCT, trailing_ws=""),
    )
    repo = _repo({"mary": "c1"})

    verdicts = _run([[sentence]], [_span(sentence, 4, 5)], [_character("c1", name="Mary")], repo)

    assert verdicts == [SpeakerVerdict("s1", 0, "Mary", "c1", "name", 1.0)]


def test_resolves_a_full_proper_name() -> None:
    sentence = _sentence(
        "s1",
        _token("Mary", POS.PROPN),
        _token("Jane", POS.PROPN),
        _token("said", POS.VERB, lemma="say"),
        _token('"', POS.PUNCT),
        _token("Hello", POS.INTJ),
        _token('"', POS.PUNCT),
    )
    repo = _repo({"mary jane": "c1"})

    verdicts = _run([[sentence]], [_span(sentence, 4, 5)], [_character("c1", name="Mary Jane")], repo)

    assert verdicts[0].reference == "Mary Jane"
    assert verdicts[0].character_id == "c1"


def test_resolves_a_pronoun_by_gender() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("she", POS.PRON),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    repo = _repo()

    verdicts = _run([[sentence]], [_span(sentence, 1, 2)], [_character("c1", gender="female")], repo)

    assert verdicts == [SpeakerVerdict("s1", 0, "she", "c1", "gender", 0.8)]
    repo.find_character_by_name.assert_not_called()


def test_resolves_a_male_pronoun_by_gender() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("he", POS.PRON),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    verdicts = _run([[sentence]], [_span(sentence, 1, 2)], [_character("c1", gender="male")], _repo())

    assert verdicts == [SpeakerVerdict("s1", 0, "he", "c1", "gender", 0.8)]


def test_unresolvable_pronoun_uses_the_sentinel() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("she", POS.PRON),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    verdicts = _run(
        [[sentence]],
        [_span(sentence, 1, 2)],
        [_character("c1", gender="female"), _character("c2", gender="female")],
        _repo(),
    )

    assert verdicts == [SpeakerVerdict("s1", 0, "she", UNRESOLVED_ID, "unresolved", 0.0)]


def test_neutral_pronoun_is_unresolved() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("they", POS.PRON),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    verdicts = _run([[sentence]], [_span(sentence, 1, 2)], [_character("c1", gender="female")], _repo())

    assert verdicts[0].character_id == UNRESOLVED_ID
    assert verdicts[0].reference == "they"


def test_unknown_name_is_unresolved() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("Stranger", POS.PROPN),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    verdicts = _run([[sentence]], [_span(sentence, 1, 2)], [_character("c1")], _repo())

    assert verdicts == [SpeakerVerdict("s1", 0, "Stranger", UNRESOLVED_ID, "unresolved", 0.0)]


def test_attribution_inside_dialogue_is_ignored() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Mary", POS.PROPN, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("she", POS.PRON),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    verdicts = _run([[sentence]], [_span(sentence, 1, 2)], [_character("c1", gender="female")], _repo())

    assert verdicts[0].reference == "she"
    assert verdicts[0].character_id == "c1"


def test_no_speech_verb_is_unresolved() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("Mary", POS.PROPN, trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )

    verdicts = _run([[sentence]], [_span(sentence, 1, 2)], [_character("c1")], _repo({"mary": "c1"}))

    assert verdicts == [SpeakerVerdict("s1", 0, "", UNRESOLVED_ID, "unresolved", 0.0)]


def test_distinct_groups_get_distinct_speakers() -> None:
    sentence = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("Mary", POS.PROPN),
        _token("said", POS.VERB, lemma="say"),
        _token(".", POS.PUNCT),
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hi", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("John", POS.PROPN),
        _token("said", POS.VERB, lemma="say"),
        _token(".", POS.PUNCT, trailing_ws=""),
    )
    spans = [_span(sentence, 1, 2), _span(sentence, 7, 8, group=1)]

    verdicts = _run(
        [[sentence]],
        spans,
        [_character("c1", name="Mary"), _character("c2", name="John")],
        _repo({"mary": "c1", "john": "c2"}),
    )

    assert verdicts == [
        SpeakerVerdict("s1", 0, "Mary", "c1", "name", 1.0),
        SpeakerVerdict("s1", 1, "John", "c2", "name", 1.0),
    ]


def test_every_sentence_in_a_group_gets_the_same_speaker() -> None:
    first = _sentence(
        "s1",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("Hello", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT),
        _token("she", POS.PRON),
        _token("said", POS.VERB, lemma="say", trailing_ws=""),
        _token(".", POS.PUNCT, trailing_ws=""),
    )
    second = _sentence(
        "s2",
        _token('"', POS.PUNCT, trailing_ws=""),
        _token("And", POS.INTJ, trailing_ws=""),
        _token("goodbye", POS.INTJ, trailing_ws=""),
        _token('"', POS.PUNCT, trailing_ws=""),
    )

    spans = [_span(first, 1, 2), _span(second, 1, 3, sentence_index=1, continues=True)]

    verdicts = _run(
        [[first, second]],
        spans,
        [_character("c1", gender="female")],
        _repo(),
    )

    assert verdicts == [
        SpeakerVerdict("s1", 0, "she", "c1", "gender", 0.8),
        SpeakerVerdict("s2", 0, "she", "c1", "gender", 0.8),
    ]
