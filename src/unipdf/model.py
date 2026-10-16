"""The document model (REQUIREMENTS §5.9).

Coordinates are PDF points with PyMuPDF's top-left origin; boxes are
`(x0, y0, x1, y1)`. Indices are 0-based. Glyphs, runs, words and lines are
numbered per page; a word names its glyphs by these indices and, for D-13,
by their glyph ids.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from unipdf.issues import Issue

SCHEMA_VERSION = "0.1"
PAGE_BREAK = "\n\n--- Page Break ---\n\n"

Box = tuple[float, float, float, float]


def union(boxes) -> Box | None:
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


@dataclass
class Glyph:
    """One drawn glyph (UP-EX-1), or one ActualText group (UP-EX-7).

    `text` is exactly what `rawdict` gives for it after repair, and may be
    several code points (UP-EX-4). Origin is the pen position from
    `texttrace`; the box is `rawdict`'s (D-14)."""

    index: int
    text: str
    glyph_id: int | None
    origin: tuple[float, float]
    bbox: Box
    font: str
    size: float
    block: int  # rawdict block number
    line: int  # rawdict line number in the block
    render_mode: int | None = None  # texttrace type: 0 fill, 1 stroke, 2 both, 3 invisible
    repeats: list[int] = field(default_factory=list)  # render types of passes drawn again
    line_width: float | None = None  # of the stroking pass, if any
    color: int | None = None
    opacity: float | None = None
    seqno: int | None = None
    synthetic: bool = False  # a space MuPDF generated (UP-EX-5)
    actual_text: bool = False  # /ActualText replacement text (UP-EX-7)
    actual_text_glyph_ids: list[int] | None = None  # the glyphs that text replaces
    unattributed: bool = False  # the converter dropped it (UP-AL-7)

    @property
    def invisible(self) -> bool:
        return self.render_mode == 3


@dataclass
class Run:
    """A conversion unit (UP-CV-1): consecutive glyphs of one font on one
    `rawdict` line. `pieces` is its provenance: each piece of output text with
    the glyphs it came from."""

    index: int
    block: int
    line: int
    font: str
    converter: str | None
    rule: int | str
    raw: str
    text: str
    glyphs: list[int]
    pieces: list[tuple[str, list[int]]]
    actual_text: bool = False  # holds ActualText glyphs, which bypassed the converter
    # its text is Unicode in logical order: a converter made it, or the repair
    # made or vouched for the map (rule 1, sound map). Otherwise it is unknown:
    # an unconverted font can hand out its glyphs in visual order
    logical: bool = False
    error: str | None = None


@dataclass
class Word:
    index: int
    line: int
    text: str
    raw_text: str
    bbox: Box | None
    glyphs: list[int]
    glyph_ids: list[int]
    fonts: list[str]
    size: float | None
    bbox_level: str = "word"
    joined_from: list[str] | None = None
    join_rules: list[str] | None = None  # the rule of each removed space
    unattributed: list[int] = field(default_factory=list)


@dataclass
class Line:
    """An output line: a visual row of `rawdict` lines (UP-LY-2), or one
    `rawdict` line with `rawdict_lines=True`."""

    index: int
    block: int
    bbox: Box | None
    text: str
    words: list[int]
    sources: list[tuple[int, int]]  # (block, line) of the rawdict lines in it


@dataclass
class Page:
    index: int
    width: float
    height: float
    rotation: int
    blocks: list[int] = field(default_factory=list)  # text block numbers, in order
    lines: list[Line] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    runs: list[Run] = field(default_factory=list)
    glyphs: list[Glyph] = field(default_factory=list)

    def text(self) -> str:
        by_block: dict[int, list[str]] = {b: [] for b in self.blocks}
        for line in self.lines:
            by_block[line.block].append(line.text)
        return "\n\n".join("\n".join(lines) for lines in by_block.values())


@dataclass
class Font:
    """What M2 knows of a font: its name and how it is converted (UP-FN-5).
    Font-program metadata arrives in M4 (UP-FN-1)."""

    name: str
    converter: str | None
    rule: int | str
    matched: str | None
    repaired: bool
    repaired_as: str | None


@dataclass
class Document:
    source: dict[str, Any]
    options: dict[str, Any]
    pages: list[Page]
    fonts: list[Font]
    issues: list[Issue]
    repaired: dict[str, str] | None = None

    def text(self) -> str:
        return PAGE_BREAK.join(page.text() for page in self.pages)

    def iter_words(self):
        for page in self.pages:
            yield from page.words

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **_rounded(asdict(self))}

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _rounded(obj):
    if isinstance(obj, float):
        return round(obj, 3)
    if isinstance(obj, dict):
        return {k: _rounded(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_rounded(v) for v in obj]
    return obj
