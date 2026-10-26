"""What a pipeline relies on: input that is not a PDF, rotated pages, the
glyph-free JSON (docs/USAGE.md)."""

import json

import pymupdf
import pytest
from corpusdata import corpus_pdfs

import unipdf
from unipdf.cli import main

C002 = next(p for e, p in corpus_pdfs() if e["id"] == "c002")


def test_a_file_that_is_not_a_pdf_is_an_error(tmp_path):
    # pymupdf opens a .md or .txt as a text document unless told otherwise
    md = tmp_path / "notes.md"
    md.write_text("# not a pdf\n", encoding="utf-8")
    with pytest.raises(pymupdf.FileDataError):
        unipdf.open(md)
    with pytest.raises(pymupdf.FileDataError):
        unipdf.open(md.read_bytes())
    assert main(["text", str(md)]) == 1
    assert main(["text", "-p", "1", str(md)]) == 1


def rotated_pdf(rotation: int) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Hello world", fontsize=24)
    page.set_rotation(rotation)
    return doc.tobytes()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_boxes_are_where_the_page_is_displayed(rotation):
    data = rotated_pdf(rotation)
    page = unipdf.open(data).pages[0]
    shown = pymupdf.open(stream=data)[0]
    assert (page.width, page.height) == (shown.rect.width, shown.rect.height)
    # the words' boxes hold the ink of the page as it is rendered
    found = {w[4]: pymupdf.Rect(w[:4]) * shown.rotation_matrix
             for w in shown.get_text("words")}
    assert [w.text for w in page.words] == ["Hello", "world"]
    for w in page.words:
        box = pymupdf.Rect(w.bbox)
        assert box in pymupdf.Rect(0, 0, page.width, page.height)
        assert box.intersects(found[w.text])


def test_json_without_glyphs():
    doc = unipdf.open(C002, pages=[0])
    full, slim = doc.to_dict(), doc.to_dict(glyphs=False)
    assert "glyphs" in full["pages"][0] and "runs" in full["pages"][0]
    assert "glyphs" not in slim["pages"][0] and "runs" not in slim["pages"][0]
    assert slim["pages"][0]["words"] == full["pages"][0]["words"]
    assert len(doc.to_json(glyphs=False)) < len(doc.to_json()) / 2


def test_cli_json_without_glyphs(capsys):
    assert main(["json", "--no-glyphs", "-p", "1", str(C002)]) == 0
    page = json.loads(capsys.readouterr().out)["pages"][0]
    assert "glyphs" not in page and page["words"]
