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


def test_words_tsv(capsys):
    assert main(["words", "-p", "1", str(corpus_pdf("c003"))]) == 0
    rows = [r.split("\t") for r in capsys.readouterr().out.splitlines()]
    assert rows[0] == ["page", "line", "word", "x0", "y0", "x1", "y1", "font", "size", "bold",
                       "italic", "region", "text", "raw_text"]
    assert rows[1][:3] == ["1", "1", "1"]
    assert rows[1][11:13] == ["", "हिंदी"]
    assert all(len(r) == len(rows[0]) for r in rows)


def test_words_json(capsys):
    import json

    assert main(["words", "--format", "json", str(corpus_pdf("c006"))]) == 0
    records = json.loads(capsys.readouterr().out)
    assert records[0]["text"] == "पश्चिम"
    assert records[0]["glyph_ids"] == [269, 302, 686, 273]  # श्चि is ActualText
    assert records[0]["glyphs"] == [1, 2, 3]


def test_glyphs_tsv_links_words(capsys):
    assert main(["glyphs", "-p", "1", str(corpus_pdf("c002"))]) == 0
    rows = [r.split("\t") for r in capsys.readouterr().out.splitlines()]
    head = rows[0]
    assert head[:3] == ["page", "glyph", "word"] and head[-1] == "raw_text"
    assert all(len(r) == len(head) for r in rows)
    assert [r[1] for r in rows[1:]] == [str(i) for i in range(1, len(rows))]
    gid = head.index("glyph_id")
    assert any(r[gid] for r in rows[1:])


def test_json_command(tmp_path):
    import json

    out = tmp_path / "doc.json"
    assert main(["json", "-p", "1", str(corpus_pdf("c003")), "-o", str(out)]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["schema_version"] == "0.1" and d["options"]["pages"] == [0]


def test_cell_escapes():
    from unipdf.cli import cell

    assert cell("a\tb\nc\\d\x01") == "a\\tb\\nc\\\\d\\x01"
    assert cell(True) == "1" and cell(None) == "" and cell(12.3456) == "12.35"
    assert cell([1, 2]) == "1 2"


def test_missing_text_summary(capsys):
    # UP-CLI-2: c011's DVB-TTYogesh is left out (D-19); exit 0
    assert main(["text", "-p", "1", str(corpus_pdf("c011"))]) == 0
    out, err = capsys.readouterr()
    assert "DVB-TTYogesh is a legacy 8-bit font (dv-tt)" in err and "(legacy_font)" in err
    assert "DVB-TTYogesh+1" not in err  # counted with DVB-TTYogesh
    assert "⟦8bit:1⟧" in out
    assert main(["text", str(corpus_pdf("c002"))]) == 0
    assert capsys.readouterr().err == ""


def test_regions(capsys):
    import json

    assert main(["regions", "-p", "1", str(corpus_pdf("c011"))]) == 0
    rows = [r.split("\t") for r in capsys.readouterr().out.splitlines()]
    assert rows[0] == ["page", "region", "line", "x0", "y0", "x1", "y1", "font", "words",
                       "raw_text"]
    assert [r[1] for r in rows[1:4]] == ["1", "2", "3"]
    assert main(["regions", "--format", "json", "-p", "1", str(corpus_pdf("c011"))]) == 0
    first = json.loads(capsys.readouterr().out)[0]
    assert first["region"] == 1 and first["words"] == [1, 2, 3]
    assert main(["words", "-p", "1", str(corpus_pdf("c011"))]) == 0
    word = capsys.readouterr().out.splitlines()[1].split("\t")
    assert word[11:13] == ["1", ""]  # region 1, no text


def test_keep_legacy(capsys):
    assert main(["text", "--keep-legacy", "-p", "1", str(corpus_pdf("c011"))]) == 0
    out, err = capsys.readouterr()
    assert "8bit" not in out and "legacy_font" not in err


def test_unreadable_pdf_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert main(["words", str(bad)]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_verbose_before_or_after_command(capsys):
    from unipdf.cli import build_parser

    for argv in (["-v", "text", "x.pdf"], ["text", "-v", "x.pdf"]):
        assert build_parser().parse_args(argv).verbose is True
    assert build_parser().parse_args(["text", "x.pdf"]).verbose is False
