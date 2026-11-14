"""Tests for the inline formatting value types."""

import pytest

from dockb.models.formatting import Family, FormatRun, Style, Weight, validate_size


def test_style_values():
    assert Style.ITALIC.value == "italic"
    assert Style.UNDERLINE.value == "underline"
    assert Style.NORMAL.value == "normal"
    assert Style._.value == ""


def test_weight_values():
    assert Weight.BOLD.value == "bold"
    assert Weight.NORMAL.value == "normal"
    assert Weight._.value == ""


def test_family_values():
    assert Family.MONOSPACE.value == "monospace"
    assert Family.NORMAL.value == "normal"
    assert Family._.value == ""


def test_format_run_defaults_to_unset():
    run = FormatRun(0, 3)
    assert run.style is Style._
    assert run.weight is Weight._
    assert run.family is Family._
    assert run.size == ""


@pytest.mark.parametrize("size", ["", "0.5em", "1em", "2em", "12.25em"])
def test_validate_size_accepts(size):
    assert validate_size(size) == size


@pytest.mark.parametrize("size", ["0em", "0.0em", "-1em", "1", "em", "1.5", "1 px", "1EM", "1rem"])
def test_validate_size_rejects(size):
    with pytest.raises(ValueError):
        validate_size(size)
