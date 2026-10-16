"""indic2unicode's regression.py as tests (UP-VF-1): each converter turns
tests/i2u/testdata/<font> into exactly tests/i2u/expected/<font>.

Devanagari converters are the release gate (D-6). The other scripts are
shipped unchanged (D-9) and run as a smoke test; they must pass too, but a
failure there says the absorption broke, not that unipdf's scope did."""

from pathlib import Path

import pytest

from unipdf.i2u.fontconv import FontConv

DATA = Path(__file__).parent / "i2u"

# the converters of Hindi and Marathi
DEVANAGARI = {
    "abhishek", "arialuni", "arialuni_glyphs", "aryan2", "chanakya", "dvotsurekh",
    "mangal_glyphs", "nirmalaui", "nirmalaui_glyphs", "sakal", "surekh", "yogesh",
}

FONTS = sorted(p.name for p in (DATA / "testdata").iterdir())


def read(path):
    # regression.py reads and writes with codecs.open, which does no newline
    # translation
    with path.open(encoding="utf-8", newline="") as f:
        return f.read()


@pytest.fixture(scope="module")
def fontconv():
    return FontConv()


def test_every_testdata_has_expected():
    assert FONTS == sorted(p.name for p in (DATA / "expected").iterdir())
    assert len(FONTS) == 41


@pytest.mark.parametrize(
    "font",
    [pytest.param(f, marks=pytest.mark.gate if f in DEVANAGARI else pytest.mark.smoke) for f in FONTS],
)
def test_converter(fontconv, font):
    out = fontconv.to_unicode(font, read(DATA / "testdata" / font))
    assert out == read(DATA / "expected" / font)


def test_devanagari_set_is_known(fontconv):
    assert DEVANAGARI <= set(FONTS)
    assert DEVANAGARI <= set(fontconv.converters)
