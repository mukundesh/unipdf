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

Words with a glyph in a legacy 8-bit font (D-19) keep their box and raw text
but get no text. Consecutive ones on a line make a legacy region, and the
line's text holds one placeholder (`⟦8bit:N⟧`) in place of the region.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from itertools import chain

from unipdf.attributes import font_run, word_attributes
from unipdf.convert.legacy import PLACEHOLDER
from unipdf.convert.resolve import RULE_LEGACY
from unipdf.issues import JOINED_WORDS, IssueBag
from unipdf.model import Cluster, FontRun, Glyph, LegacyRegion, Line, Page, Run, Word, union
from unipdf.pdf.glyphs import RawLine

# characters that cannot begin a Devanagari word (UP-LY-5 J1)
J1_MARKS = frozenset(
    chr(c)
    for c in chain(range(0x0900, 0x0904), range(0x093A, 0x0950), range(0x0951, 0x0958),
                   range(0x0962, 0x0964))
)
J1, J2 = "J1", "J2"
VIRAMA = "\u094d"


@dataclass
class _Tok:
    text: str
    glyphs: set[int]
    space: bool
    generated: bool = False  # the space unipdf puts between the lines of a row
    chars: list[tuple[str, tuple[int, ...]]] = field(default_factory=list)  # with sources

    @property
    def first(self) -> tuple[int, ...]:
        """the glyphs of its first character"""
        return self.chars[0][1] if self.chars else ()


def _line_tokens(runs: list[Run]) -> list[_Tok]:
    toks: list[_Tok] = []
    for run in runs:
        for text, src in run.pieces:
            for ch in text:
                sp = ch.isspace()
                if toks and toks[-1].space == sp:
                    toks[-1].text += ch
                    toks[-1].glyphs.update(src)
                    toks[-1].chars.append((ch, tuple(src)))
                else:
                    toks.append(_Tok(ch, set(src), sp, chars=[(ch, tuple(src))]))
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
            toks[-1].chars.extend(lt[0].chars)
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


def _is_consonant(ch: str) -> bool:
    c = ord(ch)
    return 0x0915 <= c <= 0x0939 or 0x0958 <= c <= 0x095F or 0x0978 <= c <= 0x097F


def _continues(prev: str, ch: str) -> bool:
    """whether ch belongs to the akshara prev is in"""
    if ch in "\u200c\u200d" or unicodedata.category(ch) in ("Mn", "Mc", "Me"):
        return True
    return prev == VIRAMA and _is_consonant(ch)


def aksharas(chars: list[tuple[str, tuple[int, ...]]]) -> list[tuple[str, set[int]]]:
    """a word's characters grouped into aksharas (UP-AL-5): a consonant with
    the consonants it is joined to by virama and its signs, an independent
    vowel with its signs. Any other character is one of its own"""
    out: list[tuple[str, set[int]]] = []
    prev = ""
    for ch, src in chars:
        if out and _continues(prev, ch):
            out[-1] = (out[-1][0] + ch, out[-1][1] | set(src))
        else:
            out.append((ch, set(src)))
        prev = ch
    return out


def _clusters(w: _Word, glyphs: list[Glyph]) -> list[Cluster]:
    chars = [c for p in w.parts for c in p.chars]
    out = []
    for text, src in aksharas(chars):
        ink = [glyphs[i] for i in sorted(src)
               if not glyphs[i].synthetic and not glyphs[i].text.isspace()]
        out.append(Cluster(text, union(g.bbox for g in ink), sorted(src)))
    return out


def _font_runs(w: _Word, gl: list[Glyph], glyphs: list[Glyph], font_of) -> list[FontRun]:
    """the word's glyphs in consecutive same-font groups, each with the
    converted characters whose first source glyph is in it"""
    groups: list[list[Glyph]] = []
    for g in gl:
        if groups and groups[-1][-1].font == g.font:
            groups[-1].append(g)
        else:
            groups.append([g])
    group_of = {g.index: k for k, grp in enumerate(groups) for g in grp}
    texts = [""] * len(groups)
    for p in w.parts:
        for ch, src in p.chars:
            if src and min(src) in group_of:
                texts[group_of[min(src)]] += ch
    return [font_run(grp[0].font, font_of(grp[0].font), grp, texts[k])
            for k, grp in enumerate(groups)]


def _ink(gl: list[Glyph]) -> list[Glyph]:
    return [g for g in gl if not g.synthetic and not g.text.isspace()]


def _is_legacy_word(gl: list[Glyph], legacy: set[str]) -> bool:
    """a word with an ink glyph in a legacy font (D-19)"""
    return any(g.font in legacy for g in _ink(gl))


def _make_word(index: int, line_index: int, w: _Word, glyphs: list[Glyph],
               extra: list[int], coarse: set[int], font_of, legacy: set[str]) -> Word:
    gset = set().union(*(p.glyphs for p in w.parts), extra)
    gl = [glyphs[i] for i in sorted(gset)]
    ink = _ink(gl)
    is_legacy = _is_legacy_word(gl, legacy)
    ids: list[int] = []
    for g in gl:
        if g.actual_text:
            ids.extend(g.actual_text_glyph_ids or [])
        elif g.glyph_id is not None:
            ids.append(g.glyph_id)
    sizes = Counter(g.size for g in ink)
    runs = _font_runs(w, gl, glyphs, font_of)
    if is_legacy:
        for fr in runs:
            fr.text = ""
    bold, bold_ev, italic, italic_ev = word_attributes(runs)
    return Word(
        index=index,
        line=line_index,
        text="" if is_legacy else w.text,
        raw_text="".join(g.text for g in gl),
        bbox=union(g.bbox for g in ink),
        glyphs=[g.index for g in gl],
        glyph_ids=ids,
        fonts=list(dict.fromkeys(g.font for g in gl)),
        size=sizes.most_common(1)[0][0] if sizes else None,
        joined_from=[p.text for p in w.parts] if len(w.parts) > 1 else None,
        join_rules=list(w.rules) or None,
        unattributed=sorted(extra),
        # where every glyph has its own provenance (UP-AL-5)
        clusters=None if is_legacy or gset & coarse else _clusters(w, glyphs),
        sizes=sorted(sizes),
        font_runs=runs,
        bold=bold,
        bold_evidence=bold_ev,
        italic=italic,
        italic_evidence=italic_ev,
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


def _regions(page: Page, line_index: int, words: list[Word], legacy: set[str]) -> None:
    """consecutive legacy words of a line -> legacy regions of the page"""
    group: list[Word] = []
    for w in [*words, None]:
        if w is not None and _is_legacy_word([page.glyphs[gi] for gi in w.glyphs], legacy):
            group.append(w)
            continue
        if group:
            region = LegacyRegion(
                index=len(page.legacy_regions), line=line_index,
                bbox=union(x.bbox for x in group),
                fonts=list(dict.fromkeys(f for x in group for f in x.fonts if f in legacy)),
                words=[x.index for x in group],
                raw_text=" ".join(x.raw_text for x in group))
            page.legacy_regions.append(region)
            for x in group:
                x.region = region.index
            group = []


def _line_text(toks: list[_Tok], dropped: set[int], tok_word: dict[int, int],
               words: list[Word]) -> str:
    """the row's text, a legacy region's words and the spaces between them
    given as one placeholder"""
    region_at: list[int | None] = [None] * len(toks)  # the region a token belongs to
    for ti, wi in tok_word.items():
        region_at[ti] = words[wi].region
    prev = None  # the region of the last word
    for ti in range(len(toks)):  # a space between two words of one region
        if not toks[ti].space:
            prev = region_at[ti]
        elif prev is not None:
            nxt = next((region_at[k] for k in range(ti + 1, len(toks)) if not toks[k].space),
                       None)
            if nxt == prev:
                region_at[ti] = prev
    out = []
    for ti, t in enumerate(toks):
        if ti in dropped:
            continue
        r = region_at[ti]
        if r is None:
            out.append(t.text)
        elif ti == 0 or region_at[ti - 1] != r:
            out.append(PLACEHOLDER.format(r + 1))
    return "".join(out)


def layout_page(
    page: Page,
    raw_lines: list[RawLine],
    runs: list[Run],
    rows: list[list[RawLine]],
    issues: IssueBag,
    join: bool = True,
    j2: float | None = None,
    font_of=lambda name: None,
) -> None:
    """fill page.lines and page.words from rows of rawdict lines. font_of(name)
    gives the font record that bold and italic come from"""
    glyphs = page.glyphs
    legacy = {g.font for g in glyphs
              if getattr(font_of(g.font), "rule", None) == RULE_LEGACY}
    runs_by_line: dict[tuple[int, int], list[Run]] = {}
    logical: set[int] = set()
    coarse: set[int] = set()  # glyphs of runs with run-level provenance
    for run in runs:
        runs_by_line.setdefault((run.block, run.line), []).append(run)
        logical.update(gi for gi in run.glyphs if run.logical or glyphs[gi].actual_text)
        if run.provenance == "run":
            coarse.update(run.glyphs)

    for row in rows:
        toks = _row_tokens(row, runs_by_line)
        line_index = len(page.lines)
        words: list[_Word] = []
        tok_word: dict[int, int] = {}  # token -> its word
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
                tok_word[ti] = len(words) - 1
                dropped_seps.add(pending_sep[0])
                issues.add(severity="info", code=JOINED_WORDS, page=page.index,
                           message=f"{words[-1].parts[-2].text!r} + {tok.text!r} ({rule})",
                           context={"line": line_index, "rule": rule})
            else:
                words.append(_Word([tok]))
                tok_word[ti] = len(words) - 1
            pending_sep = None

        extra = _attach_unattributed(words, row, glyphs)
        first = len(page.words)
        for k, w in enumerate(words):
            page.words.append(_make_word(first + k, line_index, w, glyphs, extra[k], coarse,
                                         font_of, legacy))
        line_words = page.words[first:]
        if legacy:
            _regions(page, line_index, line_words, legacy)
        page.lines.append(Line(
            index=line_index,
            block=row[0].block,
            bbox=union(w.bbox for w in line_words),
            text=_line_text(toks, dropped_seps, tok_word, line_words),
            words=[w.index for w in line_words],
            sources=[(ln.block, ln.line) for ln in row],
        ))
