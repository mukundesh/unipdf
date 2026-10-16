"""Words and output lines (UP-LY-3..5, UP-AL-6/7).

Words are made after conversion: a row's converted text is split on
whitespace, each character carrying the glyphs it came from (the runs'
provenance), so a word's glyphs are the union of its characters' (UP-AL-6).
Then the spaces the extraction put inside a word are removed (D-12):

- J1, script rule: the next word starts with a character no Devanagari word
  can start with (a vowel sign, virama, nukta, anusvara, chandrabindu,
  visarga). Only where that character is known to be in logical order
  (`Run.logical`, or ActualText): an unconverted font can give its glyphs in
  visual order, where a word does start with ि (Lohit-Devanagari, c007).
- J2, geometry rule: the space is a single MuPDF-generated (synthetic) one
  and the glyphs either side of it are closer than `j2` × font size. A space
  that is a glyph of the PDF is never removed by J2. Off when `j2` is None.

Glyphs the converter dropped (UP-AL-7) join the word of their row that
contains, or is nearest to, their centre.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import chain

from unipdf.issues import JOINED_WORDS, IssueBag
from unipdf.model import Glyph, Line, Page, Run, Word, union
from unipdf.pdf.glyphs import RawLine

# characters that cannot begin a Devanagari word (UP-LY-5 J1)
J1_MARKS = frozenset(
    chr(c)
    for c in chain(range(0x0900, 0x0904), range(0x093A, 0x0950), range(0x0951, 0x0958),
                   range(0x0962, 0x0964))
)
J1, J2 = "J1", "J2"


@dataclass
class _Tok:
    text: str
    glyphs: set[int]
    space: bool
    generated: bool = False  # the space unipdf puts between the lines of a row
    first: tuple[int, ...] = ()  # the glyphs of its first character


def _line_tokens(runs: list[Run]) -> list[_Tok]:
    toks: list[_Tok] = []
    for run in runs:
        for text, src in run.pieces:
            for ch in text:
                sp = ch.isspace()
                if toks and toks[-1].space == sp:
                    toks[-1].text += ch
                    toks[-1].glyphs.update(src)
                else:
                    toks.append(_Tok(ch, set(src), sp, first=tuple(src)))
    return toks


def _row_tokens(lines: list[RawLine], runs_by_line) -> list[_Tok]:
    toks: list[_Tok] = []
    for line in lines:
        lt = _line_tokens(runs_by_line.get((line.block, line.line), []))
        if not lt:
            continue
        if toks and toks[-1].space and lt[0].space:
            toks[-1].text += lt[0].text
            toks[-1].glyphs.update(lt[0].glyphs)
            toks[-1].generated = False
            lt = lt[1:]
        elif toks and not toks[-1].space and not lt[0].space:
            toks.append(_Tok(" ", set(), True, generated=True))
        toks.extend(lt)
    return toks


def _j2_gap(sep: _Tok, glyphs: list[Glyph]) -> float | None:
    """gap between the glyphs either side of a lone synthetic space, in units
    of its font size; None if the space is not one"""
    if sep.generated or len(sep.text) != 1 or len(sep.glyphs) != 1:
        return None
    (s,) = sep.glyphs
    space = glyphs[s]
    if not space.synthetic or s == 0 or s + 1 >= len(glyphs):
        return None
    before, after = glyphs[s - 1], glyphs[s + 1]
    if (before.block, before.line) != (space.block, space.line) or \
            (after.block, after.line) != (space.block, space.line):
        return None
    return (after.bbox[0] - before.bbox[2]) / space.size


@dataclass
class _Word:
    parts: list[_Tok]
    rules: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts)


def _make_word(index: int, line_index: int, w: _Word, glyphs: list[Glyph],
               extra: list[int]) -> Word:
    gset = set().union(*(p.glyphs for p in w.parts), extra)
    gl = [glyphs[i] for i in sorted(gset)]
    ink = [g for g in gl if not g.synthetic and not g.text.isspace()]
    ids: list[int] = []
    for g in gl:
        if g.actual_text:
            ids.extend(g.actual_text_glyph_ids or [])
        elif g.glyph_id is not None:
            ids.append(g.glyph_id)
    sizes = Counter(g.size for g in ink)
    return Word(
        index=index,
        line=line_index,
        text=w.text,
        raw_text="".join(g.text for g in gl),
        bbox=union(g.bbox for g in ink),
        glyphs=[g.index for g in gl],
        glyph_ids=ids,
        fonts=list(dict.fromkeys(g.font for g in gl)),
        size=sizes.most_common(1)[0][0] if sizes else None,
        joined_from=[p.text for p in w.parts] if len(w.parts) > 1 else None,
        join_rules=list(w.rules) or None,
        unattributed=sorted(extra),
    )


def _attach_unattributed(words: list[_Word], lines: list[RawLine], glyphs: list[Glyph]):
    """dropped glyphs -> the word whose box holds, or is nearest to, their centre"""
    extra: list[list[int]] = [[] for _ in words]
    if not words:
        return extra
    boxes = [union(glyphs[i].bbox for p in w.parts for i in p.glyphs) for w in words]
    for line in lines:
        for gi in line.glyphs:
            g = glyphs[gi]
            if not g.unattributed:
                continue
            cx = (g.bbox[0] + g.bbox[2]) / 2

            def dist(k, cx=cx):
                b = boxes[k]
                if b is None:
                    return float("inf")
                return 0.0 if b[0] <= cx <= b[2] else min(abs(cx - b[0]), abs(cx - b[2]))

            extra[min(range(len(words)), key=dist)].append(gi)
    return extra


def layout_page(
    page: Page,
    raw_lines: list[RawLine],
    runs: list[Run],
    rows: list[list[RawLine]],
    issues: IssueBag,
    join: bool = True,
    j2: float | None = None,
) -> None:
    """fill page.lines and page.words from rows of rawdict lines"""
    glyphs = page.glyphs
    runs_by_line: dict[tuple[int, int], list[Run]] = {}
    logical: set[int] = set()
    for run in runs:
        runs_by_line.setdefault((run.block, run.line), []).append(run)
        logical.update(gi for gi in run.glyphs if run.logical or glyphs[gi].actual_text)

    for row in rows:
        toks = _row_tokens(row, runs_by_line)
        line_index = len(page.lines)
        words: list[_Word] = []
        dropped_seps: set[int] = set()
        pending_sep: tuple[int, _Tok] | None = None
        for ti, tok in enumerate(toks):
            if tok.space:
                pending_sep = (ti, tok) if words else None
                continue
            rule = None
            if join and pending_sep is not None:
                sep = pending_sep[1]
                if tok.text[0] in J1_MARKS and tok.first and logical.issuperset(tok.first):
                    rule = J1
                elif j2 is not None:
                    gap = _j2_gap(sep, glyphs)
                    if gap is not None and gap < j2:
                        rule = J2
            if rule is not None:
                words[-1].parts.append(tok)
                words[-1].rules.append(rule)
                dropped_seps.add(pending_sep[0])
                issues.add(severity="info", code=JOINED_WORDS, page=page.index,
                           message=f"{words[-1].parts[-2].text!r} + {tok.text!r} ({rule})",
                           context={"line": line_index, "rule": rule})
            else:
                words.append(_Word([tok]))
            pending_sep = None

        extra = _attach_unattributed(words, row, glyphs)
        first = len(page.words)
        for k, w in enumerate(words):
            page.words.append(_make_word(first + k, line_index, w, glyphs, extra[k]))
        line_words = page.words[first:]
        page.lines.append(Line(
            index=line_index,
            block=row[0].block,
            bbox=union(w.bbox for w in line_words),
            text="".join(t.text for ti, t in enumerate(toks) if ti not in dropped_seps),
            words=[w.index for w in line_words],
            sources=[(ln.block, ln.line) for ln in row],
        ))
