from dockb.models.chapter import Chapter
from dockb.services.semantics.chapter_hydrator import ChapterHydrator


def test_rehydrate_a_chapter_creates_the_child_paragraphs():
    paragraph1 = "This is a very short paragraph."
    paragraph2 = "This is another simple paragraph."
    doc_text = f"{paragraph1}\n\n{paragraph2}"
    chapter = Chapter()
    chapter.set_text(doc_text)
    hydrator = ChapterHydrator()
    hydrator.hydrate(chapter)
    assert chapter.paragraphs[0].get_text() == paragraph1
    assert chapter.paragraphs[1].get_text() == paragraph2


def test_rehydrate_a_chapter_creates_the_child_paragraphs_but_not_empty_paragraphs():
    paragraph1 = "This is a very short paragraph."
    paragraph2 = "This is another simple paragraph."
    doc_text = f"{paragraph1}\n\n\n\n{paragraph2}\n\n"
    chapter = Chapter()
    chapter.set_text(doc_text)
    hydrator = ChapterHydrator()
    hydrator.hydrate(chapter)
    assert chapter.paragraphs[0].get_text() == paragraph1
    assert chapter.paragraphs[1].get_text() == paragraph2


def test_rehydrate_a_chapter_creates_the_child_paragraphs_including_single_page_feeds():
    paragraph1 = "This is a very short paragraph.\nWith a page feed."
    paragraph2 = "This is another simple paragraph.\n"
    doc_text = f"{paragraph1}\n\n{paragraph2}"
    chapter = Chapter()
    chapter.set_text(doc_text)
    hydrator = ChapterHydrator()
    hydrator.hydrate(chapter)
    assert chapter.paragraphs[0].get_text() == paragraph1
    assert chapter.paragraphs[1].get_text() == paragraph2
