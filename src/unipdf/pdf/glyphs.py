"""Glyph records (UP-EX-1..7): `rawdict` characters joined to `texttrace`.

Text and boxes come from `rawdict` with the flags R uses, so the text fed to
converters is R's byte for byte (UP-EX-2). Glyph id, pen origin, render mode,
`seqno` and repeated passes come from `texttrace`, joined by D-15 (ported
from `spikes/m0/s1_join.py`, SPIKES §1.2).

`/ActualText` (UP-EX-7): R's `rawdict` gives the replacement text, not the
glyphs. A second `rawdict` with `TEXT_IGNORE_ACTUALTEXT` gives the glyphs.
The two are diffed line by line: where they differ the default characters
are ActualText. They become one record per group, carrying the glyph ids of
the glyphs it replaces. The join runs on the second extraction, which
`texttrace` agrees with glyph for glyph.
"""

from __future__ import annotations

import difflib
from collections import defaultdict
from dataclasses import dataclass, field

import pymupdf

from unipdf.issues import EXTRACTION_MISMATCH, UNJOINED_GLYPH, IssueBag
from unipdf.model import Box, Glyph, union

FLAGS = pymupdf.TEXTFLAGS_RAWDICT  # what R's get_text("dict") uses
FLAGS_GLYPHS = FLAGS | pymupdf.TEXT_IGNORE_ACTUALTEXT
TOL = 0.01  # origins that are the same point, in pt
LOOKAHEAD = 8
REPLACEMENT = 0xFFFD


@dataclass
class RawLine:
    """A `rawdict` line: the conversion unit's container (UP-LY-1)."""

    block: int
    line: int
    dir: tuple[float, float]
    wmode: int
    bbox: Box
    glyphs: list[int] = field(default_factory=list)
    baseline: float | None = None  # origin y of its longest span
    size: float | None = None  # size of its longest span


@dataclass
class PageGlyphs:
    glyphs: list[Glyph]
    blocks: list[int]  # text block numbers, in order
    lines: list[RawLine]


# ---- texttrace


@dataclass
class _Entry:
    u: int
    gid: int
    origin: tuple[float, float]
    span: dict
    repeats: list  # [(type, linewidth)] of passes that drew this span again
    used: bool = False


def trace_entries(page: pymupdf.Page) -> list[_Entry]:
    """flat `texttrace` glyphs. A span that repeats an earlier one glyph for
    glyph (fill then stroke, or an over-print) adds no entries; its render type
    and line width are recorded on the original (UP-EX-3)."""
    entries: list[_Entry] = []
    seen: dict[tuple, list] = {}
    for span in page.get_texttrace():
        sig = tuple((u, g, round(o[0], 2), round(o[1], 2)) for u, g, o, _ in span["chars"])
        if not sig:
            continue
        repeats = seen.get(sig)
        if repeats is not None:
            repeats.append((span["type"], span["linewidth"]))
            continue
        repeats = seen[sig] = []
        for u, g, o, _ in span["chars"]:
            entries.append(_Entry(u, g, (o[0], o[1]), span, repeats))
    return entries


def _near(a, b) -> bool:
    return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


class _Joiner:
    """D-15: sequence first, origin second (SPIKES §1.2)."""

    def __init__(self, entries: list[_Entry]):
        self.T = entries
        self.prev = -1
        self.at = defaultdict(list)
        for i, t in enumerate(entries):
            self.at[(round(t.origin[0]), round(t.origin[1]))].append(i)

    def _by_origin(self, origin, u) -> int | None:
        x, y = round(origin[0]), round(origin[1])
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in self.at.get((x + dx, y + dy), ()):
                    t = self.T[i]
                    if not t.used and t.u == u and _near(t.origin, origin):
                        return i
        return None

    def join(self, c: str, origin) -> _Entry | None:
        T, u = self.T, ord(c)
        succ = self.prev + 1
        while succ < len(T) and T[succ].used:
            succ += 1
        seq_ok = succ < len(T) and T[succ].u == u
        i = None
        # 1. the next glyph, at this origin or a continuation code point
        if seq_ok and (_near(T[succ].origin, origin) or T[succ].gid == -1):
            i = succ
        # 2. this character at this origin
        if i is None:
            i = self._by_origin(origin, u)
        # 3. the next glyph by sequence alone (a moved zero-advance mark)
        if i is None and seq_ok:
            i = succ
        # 4. a little further on (reordered glyphs)
        if i is None:
            j, k = succ, 0
            while j < len(T) and k < LOOKAHEAD:
                if not T[j].used:
                    if T[j].u == u:
                        i = j
                        break
                    k += 1
                j += 1
        # 5. a glyph texttrace has no Unicode for (rawdict gives its gid)
        if i is None:
            i = self._by_origin(origin, REPLACEMENT)
        if i is None:
            return None
        T[i].used = True
        self.prev = i
        return T[i]


# ---- rawdict


def _text_lines(rd: dict):
    """(block number, line number, line) of every text line, and the text block numbers"""
    blocks, lines = [], []
    for bno, block in enumerate(rd["blocks"]):
        if "lines" not in block:
            continue
        blocks.append(bno)
        for lno, line in enumerate(block["lines"]):
            lines.append((bno, lno, line))
    return blocks, lines


def _chars(line: dict) -> list[tuple[dict, dict]]:
    return [(span, c) for span in line["spans"] for c in span["chars"]]


def _key(c: dict):
    return c["c"], round(c["origin"][0], 1), round(c["origin"][1], 1)


def _align(da, ia):
    """map default characters to glyph characters: [("same", j) | ("at", g)],
    and the ActualText groups g -> (default positions, glyph positions)"""
    if [c["c"] for _, c in da] == [c["c"] for _, c in ia]:
        return [("same", i) for i in range(len(da))], []
    sm = difflib.SequenceMatcher(None, [_key(c) for _, c in da], [_key(c) for _, c in ia],
                                 autojunk=False)
    out, groups = [None] * len(da), []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                out[i1 + k] = ("same", j1 + k)
        elif i2 > i1:  # glyphs drawn under an empty ActualText give no text
            for i in range(i1, i2):
                out[i] = ("at", len(groups))
            groups.append((range(i1, i2), range(j1, j2)))
    return out, groups


def _from_entry(e: _Entry) -> dict:
    span = e.span
    width = None
    if span["type"] in (1, 2):
        width = span["linewidth"]
    else:
        width = next((w for t, w in e.repeats if t in (1, 2)), None)
    return {
        "glyph_id": None if e.gid < 0 else e.gid,
        "origin": e.origin,
        "render_mode": span["type"],
        "repeats": [t for t, _ in e.repeats],
        "line_width": width,
        "seqno": span["seqno"],
    }


def extract_page(page: pymupdf.Page, issues: IssueBag | None = None) -> PageGlyphs:
    pno = page.number
    rd = page.get_text("rawdict", flags=FLAGS)
    rdg = page.get_text("rawdict", flags=FLAGS_GLYPHS)
    blocks, lines = _text_lines(rd)
    _, glines = _text_lines(rdg)
    same_shape = [(b, li) for b, li, _ in lines] == [(b, li) for b, li, _ in glines]
    if not same_shape and issues is not None:
        issues.add(severity="warning", code=EXTRACTION_MISMATCH, page=pno,
                   message="rawdict with and without ActualText disagree on lines; "
                           "joining without ActualText detection")

    # join every glyph character to texttrace, in rawdict order
    joiner = _Joiner(trace_entries(page))
    joined: dict[int, _Entry | None] = {}  # id(char dict) -> entry
    for _, _, line in (glines if same_shape else lines):
        for _, c in _chars(line):
            if not c["synthetic"]:
                joined[id(c)] = joiner.join(c["c"], c["origin"])

    glyphs: list[Glyph] = []
    out_lines: list[RawLine] = []
    for n, (bno, lno, line) in enumerate(lines):
        da = _chars(line)
        ia = _chars(glines[n][2]) if same_shape else da
        mapping, groups = _align(da, ia)
        raw_line = RawLine(bno, lno, tuple(line["dir"]), line["wmode"], tuple(line["bbox"]))
        if line["spans"]:
            longest = max(line["spans"], key=lambda s: len(s["chars"]))
            raw_line.baseline, raw_line.size = longest["origin"][1], longest["size"]

        prev: Glyph | None = None
        prev_span = prev_group = None
        for i, (span, c) in enumerate(da):
            kind, ref = mapping[i]
            base = {"font": span["font"], "size": span["size"], "block": bno, "line": lno,
                    "color": span["color"], "opacity": span["alpha"] / 255}
            if kind == "at":
                at_pos, glyph_pos = groups[ref]
                if prev is not None and prev_group == ref and prev_span is span:
                    prev.text += c["c"]
                    continue
                gchars = [ia[j][1] for j in glyph_pos]
                entries = [joined.get(id(gc)) for gc in gchars if not gc["synthetic"]]
                entries = [e for e in entries if e is not None]
                first_part = i == at_pos.start
                g = Glyph(
                    index=len(glyphs), text=c["c"], glyph_id=None,
                    origin=tuple(c["origin"]),
                    bbox=union(tuple(gc["bbox"]) for gc in gchars)
                    or union(tuple(da[k][1]["bbox"]) for k in at_pos),
                    actual_text=True,
                    actual_text_glyph_ids=[e.gid for e in entries if e.gid >= 0]
                    if first_part else [],
                    **base,
                )
                if entries:
                    g.render_mode = entries[0].span["type"]
                    g.seqno = entries[0].span["seqno"]
            else:
                gc = ia[ref][1]
                if c["synthetic"]:
                    g = Glyph(index=len(glyphs), text=c["c"], glyph_id=None,
                              origin=tuple(c["origin"]), bbox=tuple(c["bbox"]),
                              synthetic=True, **base)
                else:
                    e = joined.get(id(gc))
                    if e is not None and e.gid == -1 and prev is not None and prev_span is span \
                            and not prev.synthetic and not prev.actual_text:
                        # a further code point of the previous glyph (UP-EX-4)
                        prev.text += c["c"]
                        prev.bbox = union([prev.bbox, tuple(c["bbox"])])
                        continue
                    g = Glyph(index=len(glyphs), text=c["c"], glyph_id=None,
                              origin=tuple(c["origin"]), bbox=tuple(c["bbox"]), **base)
                    if e is not None:
                        for k, v in _from_entry(e).items():
                            setattr(g, k, v)
                    elif issues is not None:
                        issues.add(severity="info", code=UNJOINED_GLYPH, page=pno,
                                   font=span["font"], bbox=g.bbox,
                                   message=f"no texttrace glyph for {c['c']!r} "
                                           f"U+{ord(c['c']):04X}",
                                   context={"glyph": g.index})
            glyphs.append(g)
            raw_line.glyphs.append(g.index)
            prev, prev_span, prev_group = g, span, ref if kind == "at" else None
        out_lines.append(raw_line)

    return PageGlyphs(glyphs, blocks, out_lines)
