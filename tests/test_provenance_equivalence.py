"""Tracked conversion gives to_unicode's text (UP-AL-3, UP-VF-2).

unipdf converts only through the tracked path, so this pins it to the
absorbed converters over every Devanagari testdata file: whole file in one
call, and line by line with state carried, as a PDF feeds a converter. The
corpus runs are covered by test_parity.py."""

import pytest
from test_i2u_regression import DATA, DEVANAGARI, read

from unipdf.convert.provenance import provenance_level, tracked_to_unicode
from unipdf.i2u.fontconv import FontConv

# converters that override to_unicode with no adapter yet: run-level provenance
RUN_LEVEL = {"abhishek"}
# testdata of several MB whose lexing alone takes seconds; the whole-file test
# already covers their text
BIG = {"aryan2", "surekh"}


def check(name, chunks):
    plain, tracked = FontConv().converters[name], FontConv().converters[name]
    for data in chunks:
        want = plain.to_unicode(data)
        pieces = tracked_to_unicode(tracked, data)
        assert "".join(text for text, _ in pieces) == want, data[:80]
        for text, src in pieces:
            assert not text or src, f"output {text!r} has no source"
            assert all(0 <= i < len(data) for i in src)


@pytest.mark.parametrize("name", sorted(DEVANAGARI))
def test_whole_file(name):
    check(name, [read(DATA / "testdata" / name)])


@pytest.mark.parametrize(
    "name", [pytest.param(n, marks=pytest.mark.slow) if n in BIG else n for n in sorted(DEVANAGARI)]
)
def test_line_by_line(name):
    check(name, read(DATA / "testdata" / name).splitlines(True))


def test_provenance_levels():
    conv = FontConv().converters
    assert {n for n in DEVANAGARI if provenance_level(conv[n]) == "run"} == RUN_LEVEL
