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


def corpus_pdf(pdf_id):
    return next(p for e, p in corpus_pdfs() if e["id"] == pdf_id)


@pytest.mark.parametrize("pdf_id", ["c002", "c003"])
def test_text_r_layout_is_r(tmp_path, pdf_id):
    # UP-VF-4a: the R layout reproduces the golden byte for byte
    out = tmp_path / "out.txt"
    args = ["text", "--rawdict-lines", "--no-join", "--convert-actual-text"]
    assert main([*args, str(corpus_pdf(pdf_id)), "-o", str(out)]) == 0
    txt, _ = golden_paths(pdf_id)
    assert out.read_text(encoding="utf-8") == txt.read_text(encoding="utf-8") + "\n"


def test_text_actual_text_bypasses_converter(capsys):
    # D-18: Google Docs' ActualText हि is not reordered again (R: हंिदी)
    assert main(["text", str(corpus_pdf("c003"))]) == 0
    assert capsys.readouterr().out == "हिंदी \n"


def test_text_rows(capsys):
    # UP-LY-2: MuPDF gives this printed line as several rawdict lines
    assert main(["text", "-p", "1", str(corpus_pdf("c002"))]) == 0
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert "डेअरी फार्म, मांजरी, पुणे येथील" in lines


def test_bad_input_exits_1(tmp_path, capsys):
    assert main(["text", str(tmp_path / "missing.pdf")]) == 1
    _, pdf = next(corpus_pdfs())
    assert main(["text", "-p", "x", str(pdf)]) == 1
    assert main(["text", "--font", "nosuch", str(pdf)]) == 1
