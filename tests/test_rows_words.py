"""Visual rows and word joins (UP-LY-2..5) on hand-made glyphs and runs."""

import pytest

from unipdf.issues import IssueBag
from unipdf.layout.rows import visual_rows
from unipdf.layout.words import J1_MARKS, aksharas, layout_page
from unipdf.model import Glyph, Page, Run
from unipdf.pdf.glyphs import RawLine

SIZE = 10.0


class Builder:
    """glyphs and runs of a page, one rawdict line at a time"""

    def __init__(self):
        self.glyphs: list[Glyph] = []
        self.runs: list[Run] = []
        self.lines: list[RawLine] = []

    def line(self, text, x=0.0, y=100.0, block=0, logical=True, synthetic=(), advance=5.0,
             gap_after=None, direction=(1.0, 0.0)):
        """one run, a glyph per character; `synthetic` positions are generated
        spaces; gap_after[i] widens the gap after character i"""
        lno = sum(1 for ln in self.lines if ln.block == block)
        line = RawLine(block, lno, direction, 0, (x, y - 8, x + advance * len(text), y + 2),
                       baseline=y, size=SIZE)
        first = len(self.glyphs)
        for i, ch in enumerate(text):
            g = Glyph(index=len(self.glyphs), text=ch, glyph_id=i, origin=(x, y),
                      bbox=(x, y - 8, x + advance, y + 2), font="F", size=SIZE, block=block,
                      line=lno, synthetic=i in synthetic)
            self.glyphs.append(g)
            line.glyphs.append(g.index)
            x += advance + (gap_after or {}).get(i, 0.0)
        ids = list(range(first, len(self.glyphs)))
        self.runs.append(Run(index=len(self.runs), block=block, line=lno, font="F",
                             converter="c" if logical else None, rule=1 if logical else 4,
                             raw=text, text=text, glyphs=ids,
                             pieces=[(self.glyphs[i].text, [i]) for i in ids], logical=logical))
        self.lines.append(line)
        return self

    def page(self, rows=True, join=True, j2=None):
        page = Page(0, 600, 800, 0, glyphs=self.glyphs)
        bag = IssueBag()
        layout_rows = visual_rows(self.lines) if rows else [[ln] for ln in self.lines]
        layout_page(page, self.lines, self.runs, layout_rows, bag, join=join, j2=j2)
        page.blocks = list(dict.fromkeys(ln.block for ln in page.lines))
        return page, bag


def texts(page):
    return [w.text for w in page.words]


def test_j1_marks():
    for ch in "ािीुूृॄॅॆेैॉॊोौ्ंःँ़ॢॣ":
        assert ch in J1_MARKS, f"U+{ord(ch):04X}"
    for ch in "कअआ१ॐ।. ":
        assert ch not in J1_MARKS, f"U+{ord(ch):04X}"


def test_rows_merge_same_baseline_left_to_right():
    b = Builder().line("दोन", x=200).line("एक", x=10, y=101).line("तीन", x=10, y=130)
    page, _ = b.page()
    assert [ln.text for ln in page.lines] == ["एक दोन", "तीन"]
    assert page.lines[0].sources == [(0, 1), (0, 0)]


def test_rows_tolerance_and_blocks():
    lines = Builder().line("a", y=100).line("b", y=100 + 0.2 * SIZE + 0.1).lines
    assert len(visual_rows(lines)) == 2
    lines = Builder().line("a", y=100).line("b", y=100 + 0.2 * SIZE).lines
    assert len(visual_rows(lines)) == 1
    lines = Builder().line("a").line("b", block=1).lines
    assert len(visual_rows(lines)) == 2
    lines = Builder().line("a").line("b", direction=(0.0, 1.0)).lines
    assert len(visual_rows(lines)) == 2


def test_rawdict_lines_keep_lines():
    page, _ = Builder().line("दोन", x=200).line("एक", x=10).page(rows=False)
    assert [ln.text for ln in page.lines] == ["दोन", "एक"]


def test_j1_joins_a_word_starting_with_a_sign():
    page, bag = Builder().line("मोया ा क").page()
    assert texts(page) == ["मोयाा", "क"]
    w = page.words[0]
    assert w.joined_from == ["मोया", "ा"] and w.join_rules == ["J1"]
    assert page.lines[0].text == "मोयाा क"
    assert len(bag.by_code("joined_words")) == 1


def test_j1_across_lines_of_a_row():
    page, _ = Builder().line("प्रशास", x=10).line("ी", x=200).page()
    assert texts(page) == ["प्रशासी"]


def test_j1_not_on_text_of_unknown_order():
    # an unconverted font may give its glyphs in visual order: ि does start a word
    page, _ = Builder().line("भोपाल, िदनांक", logical=False).page()
    assert texts(page) == ["भोपाल,", "िदनांक"]


def test_no_join():
    page, bag = Builder().line("मोया ा").page(join=False)
    assert texts(page) == ["मोया", "ा"]
    assert len(bag) == 0


@pytest.mark.parametrize("gap,joined", [(0.0, True), (1.4, True), (1.6, False)])
def test_j2_synthetic_space_by_gap(gap, joined):
    # रे|लवे: the space is generated, and the glyphs either side are `gap` apart
    b = Builder().line("रे लवे", synthetic={2}, advance=5.0, gap_after={1: gap - 5.0, 2: 0.0})
    page, _ = b.page(j2=0.15)
    assert texts(page) == (["रेलवे"] if joined else ["रे", "लवे"])
    if joined:
        assert page.words[0].join_rules == ["J2"]


def test_j2_never_removes_a_real_space():
    b = Builder().line("रे लवे", advance=5.0, gap_after={1: -5.0})
    page, _ = b.page(j2=0.15)
    assert texts(page) == ["रे", "लवे"]


def test_j2_off_by_default():
    b = Builder().line("रे लवे", synthetic={2}, gap_after={1: -5.0})
    page, _ = b.page()
    assert texts(page) == ["रे", "लवे"]


def test_word_box_and_raw_text():
    page, _ = Builder().line("ab cd", x=10, advance=5.0).page()
    a, c = page.words
    assert a.bbox == (10, 92, 20, 102) and c.bbox == (25, 92, 35, 102)
    assert (a.raw_text, a.glyphs, a.glyph_ids, a.size) == ("ab", [0, 1], [0, 1], SIZE)
    assert page.lines[0].bbox == (10, 92, 35, 102)


def test_unattributed_glyph_joins_nearest_word():
    b = Builder().line("abXcd", x=10, advance=5.0, gap_after={2: 3.0})
    run = b.runs[0]
    # the converter dropped X (index 2) and output "ab cd"
    run.pieces = [("a", [0]), ("b", [1]), (" ", [1]), ("c", [3]), ("d", [4])]
    b.glyphs[2].unattributed = True
    page, _ = b.page()
    assert texts(page) == ["ab", "cd"]
    assert page.words[0].unattributed == [2]
    assert page.words[0].bbox == (10, 92, 25, 102)
    assert page.words[1].unattributed == []


@pytest.mark.parametrize("word,want", [
    ("विद्यापीठ,", ["वि", "द्या", "पी", "ठ", ","]),
    ("अंतर्गत", ["अं", "त", "र्ग", "त"]),
    ("क्ष‍त्र", ["क्ष‍", "त्र"]),
    ("ड़ॉ", ["ड़ॉ"]),
    ("ab1", ["a", "b", "1"]),
])
def test_aksharas(word, want):
    assert [t for t, _ in aksharas([(ch, (i,)) for i, ch in enumerate(word)])] == want


def test_word_clusters_follow_provenance():
    b = Builder().line("िक", x=10, advance=5.0)
    # the converter puts the matra after its consonant: कि from glyphs 1, 0
    b.runs[0].pieces = [("क", [1]), ("ि", [0])]
    page, _ = b.page()
    (w,) = page.words
    assert w.text == "कि"
    assert [(c.text, c.glyphs, c.bbox) for c in w.clusters] == [("कि", [0, 1], (10, 92, 20, 102))]


def test_no_clusters_with_run_level_provenance():
    b = Builder().line("ab")
    b.runs[0].provenance = "run"
    page, _ = b.page()
    assert page.words[0].clusters is None
