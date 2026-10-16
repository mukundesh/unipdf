"""R is stable: for every corpus PDF, R's output equals its golden (UP-VF-3).

A failure means something R depends on changed: the absorbed converters, the
resolver, PyMuPDF. Regenerate with tools/make_golden.py only when the change
is intended, and say why in the commit."""

import json
import logging

import pytest
from corpusdata import corpus_pdfs, golden_paths

from unipdf.reference import read_reference

CASES = list(corpus_pdfs())


@pytest.mark.parametrize("entry,pdf", CASES, ids=[e["id"] for e, _ in CASES])
def test_reference_matches_golden(entry, pdf):
    if pdf is None:
        pytest.skip(f"{entry['source']} not available")
    logging.disable(logging.CRITICAL)
    txt, js = golden_paths(entry["id"])
    doc = read_reference(str(pdf))
    assert doc.text() == txt.read_text(encoding="utf-8")
    golden = json.loads(js.read_text(encoding="utf-8"))
    got = doc.to_dict()
    assert got["repaired"] == golden["repaired"]
    assert got["pages"] == golden["pages"]
