"""Bold and italic (UP-AT-1..5, UP-VF-7)."""

import logging
from collections import Counter
from functools import cache
from pathlib import Path

import pytest
import yaml
from corpusdata import corpus_pdfs

from unipdf.attributes import font_run, glyph_bold_evidence
from unipdf.model import Font, Glyph
from unipdf.pdf.fonts import FontProgram, combine
from unipdf.pipeline import read_document

PATHS = {e["id"]: p for e, p in corpus_pdfs()}
HAND = yaml.safe_load((Path(__file__).parent / "hand" / "attributes.yaml").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@cache
def page_of(pdf_id, page):
    return read_document(PATHS[pdf_id], pages=[page - 1]).pages[0]


@pytest.mark.parametrize("item", HAND, ids=[f"{h['pdf']}-{h['kind']}-{h['text']}" for h in HAND])
def test_hand_labelled(item):
    if PATHS.get(item["pdf"]) is None:
        pytest.skip(f"{item['pdf']} not available")
    words = [w for w in page_of(item["pdf"], item["page"]).words if w.text == item["text"]]
    assert words, item["text"]
    # the labelled occurrence: a word can be bold in a heading and plain below
    w = min(words, key=lambda w: sum(abs(a - b) for a, b in zip(w.bbox, item["bbox"], strict=True)))
    assert (w.bold, w.italic) == (item["bold"], item["italic"]), (w.text, w.bold_evidence,
                                                                  w.italic_evidence)
    if item["kind"] == "stroke_bold":
        assert any(e.startswith("fill_then_stroke") for e in w.bold_evidence)
    if item["kind"] == "bold_font":
        assert "font_name_bold_keyword" in w.bold_evidence


def test_hand_set_coverage():
    kinds = Counter(h["kind"] for h in HAND)
    assert all(kinds[k] >= 4 for k in ("bold_font", "stroke_bold", "italic", "plain"))


def glyph(i, **kw):
    base = {"index": i, "text": "क", "glyph_id": 1, "origin": (i * 5.0, 10),
            "bbox": (i * 5.0, 0, i * 5.0 + 5, 12), "font": "F", "size": 12.0, "block": 0, "line": 0}
    base.update(kw)
    return Glyph(**base)


def test_glyph_evidence():
    assert glyph_bold_evidence(glyph(0)) == []
    assert glyph_bold_evidence(glyph(0, repeats=[1], line_width=12 / 35)) == ["fill_then_stroke(0.029 em)"]
    assert glyph_bold_evidence(glyph(0, render_mode=2, line_width=0.5)) == ["render_mode_2"]
    assert glyph_bold_evidence(glyph(0, repeats=[0])) == ["overprinted"]
    assert glyph_bold_evidence(glyph(0, repeats=[1], line_width=0.05)) == ["thin_stroke(0.004 em)"]


def test_run_bold_needs_half_its_glyphs():
    stroked = [glyph(i, repeats=[1], line_width=0.34) for i in range(2)]
    plain = [glyph(i + 2) for i in range(3)]
    run = font_run("F", None, stroked + plain, "कककक")
    assert not run.bold and run.bold_evidence == ["fill_then_stroke(0.028 em) (2 of 5 glyphs)"]
    run = font_run("F", None, stroked + plain[:2], "कककक")
    assert run.bold and run.bold_evidence == ["fill_then_stroke(0.028 em)"]
    run = font_run("F", None, [glyph(0, repeats=[0])], "क")
    assert run.bold and run.bold_evidence == ["overprinted"]


def test_font_evidence_from_the_record():
    font = Font("X,Bold", None, 4, None, False, None, bold=True,
                bold_evidence=["font_name_bold_keyword"], italic=True,
                italic_evidence=["pdf_descriptor_italic_angle_-12"])
    run = font_run("X,Bold", font, [glyph(0)], "क")
    assert (run.bold, run.italic) == (True, True)


def test_programs_that_disagree_do_not_decide():
    bold = FontProgram(1, "A", "TrueType", "", True, False, weight=700)
    regular = FontProgram(2, "A", "TrueType", "", True, False, weight=400)
    assert combine([bold.bold_evidence("A"), regular.bold_evidence("A")]) == \
        (False, ["os2_us_weight_class_700 (1 of 2 programs)"])
    assert combine([bold.bold_evidence("A")]) == (True, ["os2_us_weight_class_700"])


def test_size_majority_and_sizes():
    page = page_of("c002", 1)
    w = page.words[0]
    assert w.size == 12.0 and w.sizes == [12.0]
