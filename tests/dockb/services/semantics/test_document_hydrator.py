from dockb.models.document import Document
from dockb.services.semantics.document_hydrator import DocumentHydrator


def test_rehydrate_a_document_creates_the_child_chapters():
    chapter1 = "This is a very short chapter."
    chapter2 = "This is another simple chapter."
    doc_text = f"{chapter1}\f\f{chapter2}"
    document = Document()
    document.set_text(doc_text)
    hydrator = DocumentHydrator()
    hydrator.hydrate(document)
    assert document.chapters[0].get_text() == chapter1
    assert document.chapters[1].get_text() == chapter2


def test_rehydrate_a_document_creates_the_child_chapters_but_not_empty_chapters():
    chapter1 = "This is a very short chapter."
    chapter2 = "This is another simple chapter."
    doc_text = f"{chapter1}\f\f\f\f{chapter2}\f\f"
    document = Document()
    document.set_text(doc_text)
    hydrator = DocumentHydrator()
    hydrator.hydrate(document)
    assert document.chapters[0].get_text() == chapter1
    assert document.chapters[1].get_text() == chapter2


def test_rehydrate_a_document_creates_the_child_chapters_including_single_page_feeds():
    chapter1 = "This is a very short chapter.\fWith a page feed."
    chapter2 = "This is another simple chapter.\f"
    doc_text = f"{chapter1}\f\f{chapter2}"
    document = Document()
    document.set_text(doc_text)
    hydrator = DocumentHydrator()
    hydrator.hydrate(document)
    assert document.chapters[0].get_text() == chapter1
    assert document.chapters[1].get_text() == chapter2
