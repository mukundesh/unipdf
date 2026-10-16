"""unipdf.convert, the string API (UP-API-2)."""

import pytest

import unipdf
from unipdf.i2u.fontconv import FontConv


def test_convert_is_indic2unicode():
    raw = "dk;Zokgh"
    assert unipdf.convert("chanakya", raw) == FontConv().to_unicode("chanakya", raw)


def test_convert_with_provenance_joins_to_convert():
    raw = "fdlku"
    pieces = unipdf.convert_with_provenance("chanakya", raw)
    assert "".join(p for p, _ in pieces) == unipdf.convert("chanakya", raw)
    assert all(src and all(0 <= i < len(raw) for i in src) for _, src in pieces)
    # ि is typed before the consonant it follows
    assert pieces[:2] == [("क", [1]), ("ि", [0])]


def test_unknown_converter():
    with pytest.raises(ValueError, match="unknown converter"):
        unipdf.convert("nosuch", "x")
    assert "sakal" in unipdf.converter_names()
