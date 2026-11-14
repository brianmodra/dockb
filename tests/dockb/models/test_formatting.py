"""Tests for the inline formatting value types."""

import pytest

from dockb.models.formatting import Family, FormatRun, Style, Weight, slice_runs, validate_size


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


@pytest.mark.parametrize("start,end", [(-1, 2), (2, 1)])
def test_format_run_rejects_a_bad_range(start, end):
    with pytest.raises(ValueError):
        FormatRun(start, end)


def test_format_run_rejects_a_bad_size():
    with pytest.raises(ValueError):
        FormatRun(0, 1, size="large")


def test_slice_runs_keeps_runs_fully_inside_and_rebases_them():
    runs = [FormatRun(0, 5, style=Style.ITALIC), FormatRun(5, 10, weight=Weight.BOLD)]

    assert slice_runs(runs, 3, 8) == [
        FormatRun(0, 2, style=Style.ITALIC),
        FormatRun(2, 5, weight=Weight.BOLD),
    ]


def test_slice_runs_drops_runs_outside_the_window():
    runs = [FormatRun(0, 5, style=Style.ITALIC)]

    assert not slice_runs(runs, 5, 10)
    assert not slice_runs(runs, 10, 20)


def test_slice_runs_clips_a_straddling_run():
    runs = [FormatRun(2, 12, family=Family.MONOSPACE)]

    assert slice_runs(runs, 3, 8) == [FormatRun(0, 5, family=Family.MONOSPACE)]


def test_slice_runs_accepts_no_runs():
    assert not slice_runs([], 0, 10)
