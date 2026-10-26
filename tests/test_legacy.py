"""Legacy 8-bit fonts are left out, as regions (D-19)."""

import logging
from types import SimpleNamespace

import pytest
from corpusdata import corpus_pdfs

from unipdf.convert.legacy import PLACEHOLDER
from unipdf.convert.resolve import RULE_LEGACY
from unipdf.layout.words import _line_text, _Tok
from unipdf.model import union
from unipdf.pipeline import read_document

# corpus PDFs with a legacy font; only c011's draws more than spaces
LEGACY = ["c001", "c011", "c014", "c015", "c022"]
PATHS = {e["id"]: p for e, p in corpus_pdfs()}


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="module", params=LEGACY)
def both(request):
    path = PATHS[request.param]
    if path is None:
        pytest.skip(f"{request.param} not available")
    logging.disable(logging.CRITICAL)
    return read_document(path), read_document(path, legacy="keep")


def test_only_legacy_fonts_change(both):
    skip, keep = both
    legacy = {f.name for f in skip.fonts if f.rule == RULE_LEGACY}
    assert legacy
    for ps, pk in zip(skip.pages, keep.pages, strict=True):
        assert len(ps.runs) == len(pk.runs)
        for rs, rk in zip(ps.runs, pk.runs, strict=True):
            assert (rs.font, rs.raw) == (rk.font, rk.raw)
            if rs.font in legacy:
                assert (rs.converter, rs.rule, rs.text) == (None, RULE_LEGACY, rs.raw)
            else:
                assert (rs.converter, rs.rule, rs.text) == (rk.converter, rk.rule, rk.text)
        assert len(ps.words) == len(pk.words)
        for ws, wk in zip(ps.words, pk.words, strict=True):
            assert (ws.raw_text, ws.bbox) == (wk.raw_text, wk.bbox)
            if ws.region is None:
                assert ws.text == wk.text
                assert not any(ps.glyphs[g].font in legacy and not ps.glyphs[g].text.isspace()
                               for g in ws.glyphs)
            else:
                assert (ws.text, ws.clusters) == ("", None)
        assert not pk.legacy_regions


def test_regions(both):
    skip, _ = both
    for page in skip.pages:
        text = page.text()
        for r in page.legacy_regions:
            words = [page.words[w] for w in r.words]
            assert r.words == list(range(r.words[0], r.words[-1] + 1))
            assert all(w.region == r.index and w.line == r.line for w in words)
            assert r.bbox == union(w.bbox for w in words)
            assert text.count(PLACEHOLDER.format(r.index + 1)) == 1
            assert PLACEHOLDER.format(r.index + 1) in page.lines[r.line].text
        assert text.count("⟦8bit:") == len(page.legacy_regions)


def test_c011_is_left_out():
    path = PATHS["c011"]
    if path is None:
        pytest.skip("c011 not available")
    doc = read_document(path, pages=[0])
    page = doc.pages[0]
    assert len(page.legacy_regions) == 38
    assert page.lines[0].text == PLACEHOLDER.format(1)
    issues = [i for i in doc.issues if i.code == "legacy_font"]
    assert [i.font for i in issues] == ["DVB-TTYogesh,Bold", "DVB-TTYogesh"]
    assert not [i for i in doc.issues if i.code == "no_converter"]


def _toks(*texts):
    return [_Tok(t, set(), t.isspace()) for t in texts]


def test_line_text_puts_one_placeholder_per_region():
    toks = _toks("क", " ", "x", " ", "y", "  ", "ख", " ", "z")
    words = [SimpleNamespace(region=r) for r in (None, 0, 0, None, 1)]
    tok_word = {0: 0, 2: 1, 4: 2, 6: 3, 8: 4}
    assert _line_text(toks, set(), tok_word, words) == "क ⟦8bit:1⟧  ख ⟦8bit:2⟧"
    # no regions: the tokens as they are, less the removed separators
    plain = [SimpleNamespace(region=None)] * 5
    assert _line_text(toks, {1}, tok_word, plain) == "कx y  ख z"
