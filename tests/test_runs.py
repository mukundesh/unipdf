"""Run assembly and conversion (UP-CV-1..5) on hand-made glyphs."""

import logging

import pytest

from unipdf.convert.runs import CONVERT, Converters, convert_line
from unipdf.issues import UNCONVERTED_CHAR, IssueBag
from unipdf.model import Glyph
from unipdf.pdf.glyphs import RawLine


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def line_of(*parts):
    """parts: (font, text, actual_text) -> glyphs, one per character (one per
    part when actual_text), and their rawdict line"""
    glyphs, line = [], RawLine(0, 0, (1.0, 0.0), 0, (0, 0, 100, 10))
    for font, text, at in parts:
        for t in [text] if at else text:
            x = 5.0 * len(glyphs)
            glyphs.append(Glyph(index=len(glyphs), text=t, glyph_id=None, origin=(x, 8),
                                bbox=(x, 0, x + 5, 10), font=font, size=10, block=0, line=0,
                                actual_text=at))
            line.glyphs.append(glyphs[-1].index)
    return glyphs, line


def test_runs_split_by_font():
    glyphs, line = line_of(("Arial", "ab", False), ("Times", "c", False), ("Arial", "d", False))
    runs = convert_line(line, glyphs, Converters(None), 0, IssueBag())
    assert [(r.font, r.raw, r.text, r.glyphs) for r in runs] == [
        ("Arial", "ab", "ab", [0, 1]), ("Times", "c", "c", [2]), ("Arial", "d", "d", [3])]
    assert all(r.converter is None and r.rule == 4 and not r.logical for r in runs)


def test_converted_run_matches_to_unicode():
    # UP-CV-3, through the tracked path, with provenance per output piece
    glyphs, line = line_of(("Mangal", "िह", False))
    convs = Converters({"Mangal": "Mangal"})
    (run,) = convert_line(line, glyphs, convs, 0, IssueBag())
    assert run.converter == "mangal_glyphs" and run.logical
    assert run.text == convs.fontconv.to_unicode("mangal_glyphs", "िह") == "हि"
    assert sorted(i for _, src in run.pieces for i in src) == [0, 1]


def test_actual_text_bypasses_the_converter():
    # D-18: the ActualText हि is logical already; the rest is converted around it
    glyphs, line = line_of(("Mangal", "हि", True), ("Mangal", "ंदी", False))
    convs = Converters({"Mangal": "Mangal"})
    (run,) = convert_line(line, glyphs, convs, 0, IssueBag())
    assert run.actual_text and run.text == "हिंदी"
    (run,) = convert_line(line, glyphs, Converters({"Mangal": "Mangal"}), 0, IssueBag(),
                          actual_text=CONVERT)
    assert run.text == "हंिदी"  # what R gives


def test_unconverted_char_is_reported():
    # UP-CV-4: a code the converter has no token for is dropped, reported, and
    # its glyph is left to geometry (UP-AL-7)
    glyphs, line = line_of(("Chanakya", "d\x01d", False))
    bag = IssueBag()
    (run,) = convert_line(line, glyphs, Converters(None, force="chanakya"), 0, bag)
    (issue,) = bag.by_code(UNCONVERTED_CHAR)
    assert issue.context == {"glyph": 1, "char": "\x01"} and issue.bbox == (5, 0, 10, 10)
    assert glyphs[1].unattributed and not glyphs[0].unattributed
    assert "\x01" not in run.text
