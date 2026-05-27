import spacy

from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type
from dockb.services.semantics.async_reconstructor import AsyncReconstructor
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.job_queue import JobQueue


def test_async_reconstructor_can_hydrate_a_document_asynchronously():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    queue.start()
    reconstructor = AsyncReconstructor(cache, queue)
    document = Document()
    chapter1_text = "The cat sat on the mat. It was cold."
    chapter2_text = "The dog looked in the window at the cat."
    document.set_text(f"{chapter1_text}\f\f{chapter2_text}")
    reconstructor.run(document)
    queue.join()
    queue.shutdown()
    print(document.chapters)
    assert len(document.chapters) == 2
    assert document.chapters[0].text == chapter1_text
    assert document.chapters[1].text == chapter2_text


def test_async_reconstructor_does_not_double_up_with_document_hydratation():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    reconstructor = AsyncReconstructor(cache, queue)
    document = Document()
    chapter1_text = "The cat sat on the mat. It was cold."
    chapter2_text = "The dog looked in the window at the cat."
    document.set_text(f"{chapter1_text}\f\f{chapter2_text}")
    reconstructor.run(document)
    jobs = queue.list_jobs()
    assert len(jobs) == 2
    document.set_text("The cat sat on the mat.")
    reconstructor.run(document)
    jobs = queue.list_jobs()
    assert len(jobs) == 3
    queue.start()
    queue.join()
    queue.shutdown()
    print(document.chapters)
    assert len(document.chapters) == 1


def test_async_reconstructor_can_hydrate_a_chapter_asynchronously():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    queue.start()
    reconstructor = AsyncReconstructor(cache, queue)
    chapter = Chapter()
    paragraph1_text = "The cat sat on the mat. It was cold."
    paragraph2_text = "The dog looked in the window at the cat."
    chapter.set_text(f"{paragraph1_text}\n\n{paragraph2_text}")
    reconstructor.run(chapter)
    queue.join()
    queue.shutdown()
    print(chapter.paragraphs)
    assert len(chapter.paragraphs) == 2
    assert chapter.paragraphs[0].text == paragraph1_text
    assert chapter.paragraphs[1].text == paragraph2_text


def test_async_reconstructor_does_not_double_up_with_chapter_hydratation():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    reconstructor = AsyncReconstructor(cache, queue)
    chapter = Chapter()
    paragraph1_text = "The cat sat on the mat. It was cold."
    paragraph2_text = "The dog looked in the window at the cat."
    chapter.set_text(f"{paragraph1_text}\n\n{paragraph2_text}")
    reconstructor.run(chapter)
    jobs = queue.list_jobs()
    assert len(jobs) == 2
    chapter.set_text("The cat sat on the mat.")
    reconstructor.run(chapter)
    jobs = queue.list_jobs()
    assert len(jobs) == 3
    queue.start()
    queue.join()
    queue.shutdown()
    print(chapter.paragraphs)
    assert len(chapter.paragraphs) == 1


def test_async_reconstructor_can_hydrate_a_paragraph_asynchronously():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    queue.start()
    reconstructor = AsyncReconstructor(cache, queue)
    paragraph = Paragraph()
    sentence1 = "The cat sat on the mat."
    sentence2 = "It was cold."
    paragraph.set_text(f"{sentence1} {sentence2}")
    reconstructor.run(paragraph)
    queue.join()
    queue.shutdown()
    print(paragraph.sentences)
    assert len(paragraph.sentences) == 2


def test_async_reconstructor_does_not_double_up_with_paragraph_hydratation():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    queue = JobQueue()
    reconstructor = AsyncReconstructor(cache, queue)
    paragraph = Paragraph()
    paragraph.set_text("The cat sat on the mat. It was cold.")
    reconstructor.run(paragraph)
    jobs = queue.list_jobs()
    assert len(jobs) == 2
    paragraph.set_text("The cat sat on the mat.")
    reconstructor.run(paragraph)
    jobs = queue.list_jobs()
    assert len(jobs) == 3
    queue.start()
    queue.join()
    queue.shutdown()
    print(paragraph.sentences)
    assert len(paragraph.sentences) == 1


def test_async_reconstructor_can_retokenise_a_sentence_asynchronously():
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
    reconstructor = AsyncReconstructor(cache, queue)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat in the café looking at the dog 😜.")
    reconstructor.run(sentence)
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


def test_async_reconstructor_does_not_double_up_with_retokenization():
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
    reconstructor = AsyncReconstructor(cache, queue)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat.")
    reconstructor.run(sentence)
    jobs = queue.list_jobs()
    assert len(jobs) == 2
    sentence.set_text("The cat sat on the mat in the café looking at the dog 😜.")
    reconstructor.run(sentence)
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
