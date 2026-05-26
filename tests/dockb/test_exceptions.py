import pytest

from dockb.exceptions import EditTextRangeError, TokenInvalidError


def test_edit_text_range_error_has_start_and_end():
    exc = EditTextRangeError("bad range", 5, 10)
    assert str(exc) == "bad range"
    assert exc.start == 5
    assert exc.end == 10


def test_token_invalid_error_message():
    exc = TokenInvalidError("invalid value")
    assert str(exc) == "invalid value"
