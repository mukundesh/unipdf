"""specs/JSON_SCHEMA.md lists exactly the fields to_json emits (UP-MD-1, -2)."""

import json
import re
from pathlib import Path

import pytest
from corpusdata import corpus_pdfs

import unipdf

SCHEMA = Path(__file__).parent.parent / "specs" / "JSON_SCHEMA.md"


def documented() -> dict[str, set[str]]:
    """section name -> the fields its table lists"""
    out: dict[str, set[str]] = {}
    section = None
    for line in SCHEMA.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif section and line.startswith("| `") and section not in ("Issue codes",):
            first = line.split("|")[1]
            out.setdefault(section, set()).update(re.findall(r"`([^`]+)`", first))
    return out


def emitted(d: dict) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {}

    def add(name, objs):
        for o in objs:
            seen.setdefault(name, set()).update(o)

    add("Document", [d])
    add("Font", d["fonts"])
    add("FontProgram", [p for f in d["fonts"] for p in f["programs"]])
    add("Issue", d["issues"])
    for page in d["pages"]:
        add("Page", [page])
        add("Line", page["lines"])
        add("Word", page["words"])
        add("Cluster", [c for w in page["words"] for c in w["clusters"] or []])
        add("FontRun", [r for w in page["words"] for r in w["font_runs"]])
        add("Run", page["runs"])
        add("Glyph", page["glyphs"])
    return seen


def corpus_pdf(pdf_id):
    return next(p for e, p in corpus_pdfs() if e["id"] == pdf_id)


@pytest.fixture(scope="module")
def doc_dict():
    # c011 has issues (no_converter), c003 ActualText
    return [json.loads(unipdf.open(corpus_pdf(i)).to_json()) for i in ("c011", "c003")]


def test_schema_lists_what_is_emitted(doc_dict):
    doc = documented()
    seen: dict[str, set[str]] = {}
    for d in doc_dict:
        for name, fields in emitted(d).items():
            seen.setdefault(name, set()).update(fields)
    assert set(seen) <= set(doc)
    for name, fields in seen.items():
        assert fields == doc[name], name
    assert doc_dict[0]["schema_version"] == unipdf.model.SCHEMA_VERSION


def test_issue_codes_are_documented(doc_dict):
    text = SCHEMA.read_text(encoding="utf-8")
    for d in doc_dict:
        for issue in d["issues"]:
            assert f"| `{issue['code']}` |" in text


def test_json_is_deterministic():
    pdf = corpus_pdf("c002")
    assert unipdf.open(pdf, pages=[0]).to_json() == unipdf.open(pdf, pages=[0]).to_json()


def test_raw_text_and_glyph_ids_in_default_json(doc_dict):
    # D-13 / UP-MD-1
    word = doc_dict[1]["pages"][0]["words"][0]
    assert word["text"] == "हिंदी"
    assert word["raw_text"] and word["glyph_ids"]
    # the ActualText group हि stands for two glyphs
    assert word["glyph_ids"] == [465, 161, 562, 145, 547]
    assert len(word["glyphs"]) == 4
