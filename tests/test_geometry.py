"""Geometry (UP-VF-5, UP-VF-6)."""

import logging
from collections import Counter
from functools import cache
from pathlib import Path

import pytest
import yaml
from corpusdata import corpus_pdfs

from unipdf.model import union
from unipdf.pipeline import read_document

CASES = list(corpus_pdfs())
PATHS = {e["id"]: p for e, p in CASES}
HAND = yaml.safe_load((Path(__file__).parent / "hand" / "words.yaml").read_text(encoding="utf-8"))
TOL = 0.5  # pt (UP-VF-6)
EPS = 1e-6


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def inside(inner, outer, tol=EPS):
    return all(inner[i] >= outer[i] - tol for i in (0, 1)) and \
        all(inner[i] <= outer[i] + tol for i in (2, 3))


@pytest.mark.parametrize("entry,pdf", CASES, ids=[e["id"] for e, _ in CASES])
def test_invariants(entry, pdf):
    if pdf is None:
        pytest.skip(f"{entry['source']} not available")
    for page in read_document(pdf).pages:
        where = f"page {page.index}"
        owners = Counter(gi for w in page.words for gi in w.glyphs)
        for g in page.glyphs:
            # every glyph is drawn on the page
            assert -EPS <= g.origin[0] <= page.width + EPS, where
            assert -EPS <= g.origin[1] <= page.height + EPS, where
            # every glyph with ink belongs to exactly one word
            if not g.synthetic and not g.text.isspace():
                assert owners[g.index] == 1, f"{where} glyph {g.index} {g.text!r}"
        for w in page.words:
            ink = [page.glyphs[i] for i in w.glyphs]
            ink = [g for g in ink if not g.synthetic and not g.text.isspace()]
            # a word's box is the union of its glyphs' boxes
            assert w.bbox == union(g.bbox for g in ink), f"{where} {w.text!r}"
            # D-14 boxes run ascender to descender, so a word at the very edge can
            # overhang the page by less than its font size, never more
            pad = w.size or 0
            assert inside(w.bbox, (0, 0, page.width, page.height), tol=pad), w.text
            for c in w.clusters or []:
                if c.bbox is not None:
                    assert inside(c.bbox, w.bbox), f"{where} {w.text!r} {c.text!r}"
            if w.clusters:
                assert "".join(c.text for c in w.clusters) == w.text
        for line in page.lines:
            words = [page.words[i] for i in line.words]
            assert line.bbox == union(w.bbox for w in words)


@cache
def page_of(pdf_id, page):
    return read_document(PATHS[pdf_id], pages=[page - 1]).pages[0]


def near(a, b):
    return all(abs(x - y) <= TOL for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize("item", HAND, ids=[f"{h['pdf']}-{h['text']}" for h in HAND])
def test_hand_checked(item):
    if PATHS.get(item["pdf"]) is None:
        pytest.skip(f"{item['pdf']} not available")
    page = page_of(item["pdf"], item["page"])
    candidates = [w for w in page.words if w.text == item["text"] and w.bbox]
    assert candidates, f"{item['text']!r} not on page {item['page']}"

    def dist(w):
        return sum(abs(x - y) for x, y in zip(w.bbox, item["bbox"], strict=True))

    w = min(candidates, key=dist)
    assert near(w.bbox, item["bbox"]), (w.bbox, item["bbox"])
    assert [c.text for c in w.clusters] == [t for t, _ in item["clusters"]]
    for c, (_, box) in zip(w.clusters, item["clusters"], strict=True):
        assert near(c.bbox, box), (c.text, c.bbox, box)


def test_hand_set_coverage():
    cases = Counter(case for h in HAND for case in h["cases"])
    assert len(HAND) >= 45
    assert all(cases[c] >= 5 for c in ("reph", "matra_i", "conjunct", "nukta", "plain"))
    assert {h["converter"] for h in HAND} >= {
        "sakal", "dvotsurekh", "nirmalaui_glyphs", "mangal_glyphs", "arialuni_glyphs"}
