import pytest

from dockb.models.document import Document

def test_edit_text_does_replace_the_text_and_invalidates_semantics():
    document = Document()
    document.apply_edit_text(0, 0, "Hello World!")
    assert document.text == "Hello World!"
    assert document.dirty
