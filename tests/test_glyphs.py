"""Glyph records (UP-EX-1..7) on corpus PDFs."""

import logging

import pymupdf
import pytest
from corpusdata import corpus_pdfs

from unipdf.issues import UNJOINED_GLYPH, IssueBag
from unipdf.pdf.glyphs import extract_page
from unipdf.pdf.repair import repair

CASES = list(corpus_pdfs())


def first_page(pdf_id):
    pdf = next(p for e, p in CASES if e["id"] == pdf_id)
    if pdf is None:
        pytest.skip(f"{pdf_id} not available")
    logging.disable(logging.CRITICAL)
    doc = pymupdf.open(pdf)
    repair(doc)
    return extract_page(doc[0])


@pytest.mark.parametrize("entry,pdf", CASES, ids=[e["id"] for e, _ in CASES])
def test_join_rate(entry, pdf):
    # plan M2 step 3: >= 99.9 % of glyphs joined to texttrace, per PDF
    if pdf is None:
        pytest.skip(f"{entry['source']} not available")
    logging.disable(logging.CRITICAL)
    doc = pymupdf.open(pdf)
    repair(doc)
    bag, total = IssueBag(), 0
    for page in doc:
        pg = extract_page(page, bag)
        total += sum(1 for g in pg.glyphs if not g.synthetic and not g.actual_text)
    assert len(bag.by_code(UNJOINED_GLYPH)) <= 0.001 * total


def test_multi_code_point_glyph_is_one_record():
    # UP-EX-4: त् is one glyph; texttrace's gid -1 continuation merges into it
    pg = first_page("c002")
    multi = {g.text: g.glyph_id for g in pg.glyphs if len(g.text) > 1}
    assert multi["त्"] == 190 and multi["द्य"] == 463


def test_fill_stroke_repeat_is_recorded_once():
    # UP-EX-3: Word's synthetic bold, a stroke pass of size / 35 over the fill
    pg = first_page("c002")
    g = pg.glyphs[0]
    assert (g.text, g.render_mode, g.repeats) == ("म", 0, [1])
    assert g.line_width == pytest.approx(g.size / 35, abs=1e-3)
    assert "".join(x.text for x in pg.glyphs[:2]) == "मह"


def test_actual_text_group():
    # UP-EX-7: Google Docs draws ि ह (glyphs 465, 161) under ActualText हि
    pg = first_page("c003")
    at = [g for g in pg.glyphs if g.actual_text]
    assert [(g.text, g.actual_text_glyph_ids, g.glyph_id) for g in at] == [("हि", [465, 161], None)]
    assert "".join(g.text for g in pg.glyphs) == "हिंदी "
