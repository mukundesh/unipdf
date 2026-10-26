"""ActualText that is not used (D-20): a Word export whose ActualText is
U+FFFD over the conjuncts and shifted by a character elsewhere, over a font
the repair rebuilds (tests/fixtures/README.md)."""

import logging
from pathlib import Path

import pytest

from unipdf.pipeline import read_document

PDF = Path(__file__).parent / "fixtures" / "word_shifted_actualtext.pdf"
WORDS = ["बुद्धिमत्ता", "क्षेत्रात", "घडविण्यासाठी", "माध्यमातून", "शाश्वत",
         "महत्त्वाकांक्षी", "दूरदृष्टीपूर्ण", "उत्पन्न", "केंद्रित", "पाण्याचा"]


@pytest.fixture(scope="module")
def doc():
    logging.disable(logging.CRITICAL)
    yield read_document(PDF)
    logging.disable(logging.NOTSET)


def test_glyphs_are_read_not_the_actual_text(doc):
    text = doc.text()
    assert "�" not in text
    for word in WORDS:
        assert word in text, word
    page = doc.pages[0]
    assert any(g.actual_text_ignored for g in page.glyphs)
    assert not any(g.actual_text for g in page.glyphs if "Sakal" in g.font)


def test_lines_that_differ_are_aligned_across_the_page(doc):
    # the extractions with and without ActualText split this page into 115
    # and 135 lines; every glyph is still joined to texttrace
    assert not [i for i in doc.issues if i.code == "unjoined_glyph"]


def test_r_reads_the_actual_text():
    logging.disable(logging.CRITICAL)
    doc = read_document(PDF, actual_text="convert")
    assert "�" in doc.text()
