"""The PDF parity gate (UP-VF-4, UP-VF-4a, UP-CV-3) over the corpus.

R's output is the golden (tests/corpus/golden, from tools/make_golden.py).
For every corpus PDF and page:

1. every run's converted text equals R's for the same run. The exceptions
   are a run whose ActualText bypassed its converter (D-18): its raw text must
   still be R's; and a run holding glyphs of an ActualText unipdf did not use
   (D-20), which reads the glyphs where R read the ActualText;
2. the page's words, with unipdf's joins undone, are R's words (R's text
   split on whitespace). Departures under D-18 are applied to R first: the
   runs of 1.'s exception take unipdf's text. In order with `rawdict_lines`;
   with visual rows, as a multiset per page, since a row orders its lines left
   to right and MuPDF does not always list them so (c023 p8, an OCR layer);
3. `rawdict_lines`, no joins, ActualText converted: R's text byte for byte.

All with `legacy="keep"`: R reads legacy 8-bit fonts, which unipdf by default
leaves out (D-19, tests/test_legacy.py).
"""

import json
import logging
from collections import Counter

import pytest
from corpusdata import corpus_pdfs, golden_paths

from unipdf.pipeline import read_document

CASES = [(e, p) for e, p in corpus_pdfs()]
IDS = [e["id"] for e, _ in CASES]


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def golden(entry):
    txt, js = golden_paths(entry["id"])
    return txt.read_text(encoding="utf-8"), json.loads(js.read_text(encoding="utf-8"))


def need(pdf, entry):
    if pdf is None:
        pytest.skip(f"{entry['source']} not available")


def r_runs(gpage):
    """R's runs of a page, in order, with the line they are on"""
    out = []
    for b, block in enumerate(gpage["blocks"]):
        for li, line in enumerate(block):
            for run in line["runs"]:
                out.append(((b, li), run))
    return out


def bypassed(run):
    return run.actual_text and run.converter is not None


def ignored(run, page):
    """a run holding glyphs of an ActualText that was not used (D-20)"""
    return any(page.glyphs[g].actual_text_ignored for g in run.glyphs)


@pytest.mark.parametrize("entry,pdf", CASES, ids=IDS)
def test_runs_equal_r(entry, pdf):
    need(pdf, entry)
    _, gold = golden(entry)
    doc = read_document(pdf, legacy="keep")
    assert len(doc.pages) == len(gold["pages"])
    for page, gpage in zip(doc.pages, gold["pages"], strict=True):
        theirs = [run for _, run in r_runs(gpage)]
        assert len(page.runs) == len(theirs), f"page {page.index}: run count"
        for ours, ref in zip(page.runs, theirs, strict=True):
            where = f"page {page.index} run {ours.index}"
            if ignored(ours, page):
                assert ours.font == ref["font"], where
                continue
            assert (ours.font, ours.raw) == (ref["font"], ref["raw"]), where
            assert (ours.converter, ours.rule) == (ref["converter"], ref["rule"]), where
            if not bypassed(ours):
                assert ours.text == ref["text"], where
                assert ours.error == ref["error"], where


def r_words_with_departures(page, gpage):
    """R's words of a page, with the runs of D-18 and D-20 given unipdf's text"""
    ours = iter(page.runs)
    blocks = []
    for block in gpage["blocks"]:
        lines = []
        for line in block:
            text = []
            for ref in line["runs"]:
                run = next(ours)
                text.append(run.text if bypassed(run) or ignored(run, page) else ref["text"])
            lines.append("".join(text))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks).split()


def unjoined(page):
    return [part for w in page.words for part in (w.joined_from or [w.text])]


@pytest.mark.parametrize("rows", [False, True], ids=["lines", "rows"])
@pytest.mark.parametrize("entry,pdf", CASES, ids=IDS)
def test_words_equal_r(entry, pdf, rows):
    need(pdf, entry)
    _, gold = golden(entry)
    doc = read_document(pdf, rawdict_lines=not rows, legacy="keep")
    for page, gpage in zip(doc.pages, gold["pages"], strict=True):
        want = r_words_with_departures(page, gpage)
        if rows:
            assert Counter(unjoined(page)) == Counter(want), f"page {page.index}"
        else:
            assert unjoined(page) == want, f"page {page.index}"
    # every removed space is recorded (UP-LY-5)
    joins = sum(len(w.joined_from) - 1 for w in doc.iter_words() if w.joined_from)
    assert joins == sum(1 for i in doc.issues if i.code == "joined_words")


@pytest.mark.parametrize("entry,pdf", CASES, ids=IDS)
def test_r_layout_is_r(entry, pdf):
    need(pdf, entry)
    txt, _ = golden(entry)
    doc = read_document(pdf, rawdict_lines=True, join=False, actual_text="convert",
                        legacy="keep")
    assert doc.text() == txt
