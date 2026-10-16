import pytest
from corpusdata import corpus_pdfs, golden_paths

from unipdf.cli import main, parse_font_map, parse_page_range


def test_parse_page_range():
    assert parse_page_range("1,3-5", 10) == [0, 2, 3, 4]
    assert parse_page_range("4-99, 2", 5) == [1, 3, 4]
    assert parse_page_range("0,11", 10) == []
    with pytest.raises(ValueError):
        parse_page_range("1-x", 10)


def test_parse_font_map():
    assert parse_font_map(["DVB-TTSurekh=surekh", "A=B=sakal"]) == {"DVB-TTSurekh": "surekh", "A=B": "sakal"}
    with pytest.raises(ValueError):
        parse_font_map(["surekh"])


def test_text_rawdict_lines_no_join_is_r(tmp_path):
    # UP-VF-4a: the R layout reproduces the golden byte for byte
    pdf = next(p for e, p in corpus_pdfs() if e["id"] == "c002")
    out = tmp_path / "out.txt"
    assert main(["text", "--rawdict-lines", "--no-join", str(pdf), "-o", str(out)]) == 0
    txt, _ = golden_paths("c002")
    assert out.read_text(encoding="utf-8") == txt.read_text(encoding="utf-8") + "\n"


def test_bad_input_exits_1(tmp_path, capsys):
    assert main(["text", str(tmp_path / "missing.pdf")]) == 1
    _, pdf = next(corpus_pdfs())
    assert main(["text", "-p", "x", str(pdf)]) == 1
    assert main(["text", "--font", "nosuch", str(pdf)]) == 1
