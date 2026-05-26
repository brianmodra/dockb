import spacy

from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type
from dockb.services.semantics.async_sentence_reconstructor import AsyncSentenceReconstructor
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.job_queue import JobQueue


def test_async_sentence_reconstructor_can_retokenise_a_sentence_asynchronously():
    expected = [
        Token(text="The", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="cat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="cat", pos=POS.NOUN),
        Token(text="sat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="sit", pos=POS.VERB),
        Token(text="on", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="on", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="mat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="mat", pos=POS.NOUN),
        Token(text="in", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="in", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="café", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="café", pos=POS.NOUN),
        Token(text="looking", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="look", pos=POS.VERB),
        Token(text="at", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="at", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="dog", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="dog", pos=POS.NOUN),
        Token(text="😜", type=Type.EXTENDED, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma="", pos=POS._),
        Token(text=".", type=Type.PUNCTUATION, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma=".", pos=POS.PUNCT),
    ]
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    queue.start()
    sentence_reconstructor = AsyncSentenceReconstructor(cache, queue)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat in the café looking at the dog 😜.")
    sentence_reconstructor.run(sentence)
    queue.join()
    queue.shutdown()
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


def test_async_sentence_reconstructor_does_not_double_up_with_retokenization():
    expected = [
        Token(text="The", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="cat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="cat", pos=POS.NOUN),
        Token(text="sat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="sit", pos=POS.VERB),
        Token(text="on", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="on", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="mat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="mat", pos=POS.NOUN),
        Token(text="in", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="in", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="café", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="café", pos=POS.NOUN),
        Token(text="looking", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="look", pos=POS.VERB),
        Token(text="at", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="at", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="dog", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="dog", pos=POS.NOUN),
        Token(text="😜", type=Type.EXTENDED, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma="", pos=POS._),
        Token(text=".", type=Type.PUNCTUATION, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma=".", pos=POS.PUNCT),
    ]
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    sentence_reconstructor = AsyncSentenceReconstructor(cache, queue)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat.")
    sentence_reconstructor.run(sentence)
    jobs = queue.list_jobs()
    assert len(jobs) == 2
    sentence.set_text("The cat sat on the mat in the café looking at the dog 😜.")
    sentence_reconstructor.run(sentence)
    jobs = queue.list_jobs()
    assert len(jobs) == 3
    queue.start()
    queue.join()
    queue.shutdown()
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
