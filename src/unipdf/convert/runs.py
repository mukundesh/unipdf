"""Run assembly and conversion (UP-CV-1..5).

A run is a maximal sequence of glyphs of one font on one `rawdict` line, as
R's same-font span merge gives it. Runs are converted in page, line and run
order with one FontConv per document, since converters keep state between
runs (sakal). Conversion goes through the tracked path (provenance.py), whose
text is pinned to `to_unicode`.

ActualText (OQ-9 option b, D-18): with `actual_text="bypass"` (default),
glyph records holding ActualText are already logical-order Unicode and are
not given to the converter; the rest of the run is converted around them in
order. `actual_text="convert"` is R's behaviour.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from unipdf.convert.provenance import provenance_level, tracked_to_unicode
from unipdf.convert.resolve import (
    RULE_NONE,
    RULE_REPAIRED,
    SOUND_MAP,
    ConverterResolver,
    Resolution,
    is_glyphs_converter,
    strip_subset,
)
from unipdf.i2u.fix_tounicode import font_lookup_key
from unipdf.i2u.fontconv import FontConv
from unipdf.issues import (
    CONVERTER_ERROR,
    NO_CONVERTER,
    PROVENANCE_UNAVAILABLE,
    UNCONVERTED_CHAR,
    IssueBag,
)
from unipdf.model import Font, Glyph, Run
from unipdf.pdf.fonts import FontProgram, combine, name_evidence
from unipdf.pdf.glyphs import RawLine

BYPASS, CONVERT = "bypass", "convert"

# share of a font's characters in legacy ranges above which a font with no
# converter is reported (UP-CLI-2)
LEGACY_SHARE = 0.2


class Converters:
    """The converters of one document, and the font record of each font name
    (its converter, its PDF font objects, its bold/italic evidence)."""

    def __init__(
        self,
        repaired: Mapping[str, str] | None,
        force: str | None = None,
        font_map: Mapping[str, str] | None = None,
        programs: Mapping[str, list[FontProgram]] | None = None,
    ):
        self.fontconv = FontConv()
        self.resolver = ConverterResolver(self.fontconv.converters, force=force,
                                          font_map=font_map)
        self.repaired = repaired
        self.programs = programs or {}
        self.resolutions: dict[str, Resolution] = {}
        self.records: dict[str, Font] = {}
        self._run_level_reported: set[str] = set()

    def resolve(self, font: str) -> Resolution:
        res = self.resolutions.get(font)
        if res is None:
            res = self.resolutions[font] = self.resolver.resolve(font, self.repaired)
        return res

    def font(self, name: str) -> Font:
        rec = self.records.get(name)
        if rec is not None:
            return rec
        res = self.resolve(name)
        repaired_as = None
        if self.repaired is not None:
            repaired_as = self.repaired.get(strip_subset(name))
        progs = self.programs.get(strip_subset(name), [])
        if progs:
            bold, bold_ev = combine([p.bold_evidence(name) for p in progs])
            italic, italic_ev = combine([p.italic_evidence(name) for p in progs])
        else:
            bold_ev, italic_ev = name_evidence(name)
            bold, italic = bool(bold_ev), bool(italic_ev)
        rec = self.records[name] = Font(
            name, res.converter, res.rule, res.matched, repaired_as is not None, repaired_as,
            programs=progs, bold=bold, bold_evidence=bold_ev, italic=italic,
            italic_evidence=italic_ev,
        )
        return rec

    def fonts(self) -> list[Font]:
        return [self.font(name) for name in self.resolutions]


def _error_counts(conv) -> Counter:
    """characters the converter reported as having no token, so far"""
    counts = Counter(conv.errchars)
    for sub in getattr(conv, "scriptobjs", {}).values():
        counts.update(getattr(sub, "errchars", {}))
    return counts


def _segments(glyphs: list[Glyph], bypass: bool):
    """split a run's glyphs where ActualText starts or ends"""
    if not bypass or not any(g.actual_text for g in glyphs):
        return [(False, glyphs)]
    out: list[tuple[bool, list[Glyph]]] = []
    for g in glyphs:
        if out and out[-1][0] == g.actual_text:
            out[-1][1].append(g)
        else:
            out.append((g.actual_text, [g]))
    return out


def _convert(conv_name, convs: Converters, glyphs: list[Glyph], run: Run, page: int,
             issues: IssueBag):
    """tracked conversion of one segment; pieces with glyph indices"""
    conv = convs.fontconv.converters[conv_name]
    data = "".join(g.text for g in glyphs)
    owner = [g.index for g in glyphs for _ in g.text]
    if provenance_level(conv) == "run":
        run.provenance = "run"
    if run.provenance == "run" and conv_name not in convs._run_level_reported:
        convs._run_level_reported.add(conv_name)
        issues.add(severity="info", code=PROVENANCE_UNAVAILABLE, page=page, font=run.font,
                   message=f"{conv_name}: no index map, boxes are per run")
    before = _error_counts(conv)
    try:
        tracked = tracked_to_unicode(conv, data)
    except Exception as e:  # noqa: BLE001 - UP-CV-5: the raw text stands
        run.error = f"{type(e).__name__}: {e}"
        issues.add(severity="warning", code=CONVERTER_ERROR, page=page, font=run.font,
                   message=f"{conv_name} failed on {data!r}: {run.error}")
        return [(g.text, [g.index]) for g in glyphs]

    covered = set()
    for _, src in tracked:
        covered.update(src)
    # characters the lexer reported and skipped (UP-CV-4); others that give
    # no output (t_ignore rules, tokens with no text) are by design
    reported = _error_counts(conv) - before
    by_index = {g.index: g for g in glyphs}
    for i, ch in enumerate(data):
        if i not in covered and reported[ch] > 0:
            reported[ch] -= 1
            g = by_index[owner[i]]
            issues.add(severity="warning", code=UNCONVERTED_CHAR, page=page, font=run.font,
                       bbox=g.bbox,
                       message=f"{conv_name} has no token for U+{ord(ch):04X} {ch!r}",
                       context={"glyph": g.index, "char": ch})
    return [(text, sorted({owner[i] for i in src})) for text, src in tracked]


def convert_line(
    line: RawLine,
    glyphs: list[Glyph],
    convs: Converters,
    page: int,
    issues: IssueBag,
    first_index: int = 0,
    actual_text: str = BYPASS,
) -> list[Run]:
    runs: list[Run] = []
    current: list[Glyph] = []
    groups: list[list[Glyph]] = []
    for gi in line.glyphs:
        g = glyphs[gi]
        if current and current[-1].font != g.font:
            groups.append(current)
            current = []
        current.append(g)
    if current:
        groups.append(current)

    for run_glyphs in groups:
        font = run_glyphs[0].font
        res = convs.resolve(font)
        raw = "".join(g.text for g in run_glyphs)
        run = Run(
            index=first_index + len(runs), block=line.block, line=line.line, font=font,
            converter=res.converter, rule=res.rule, raw=raw, text="",
            glyphs=[g.index for g in run_glyphs], pieces=[],
            actual_text=any(g.actual_text for g in run_glyphs),
            logical=res.converter is not None or res.rule == RULE_REPAIRED
            or res.matched == SOUND_MAP,
        )
        if res.converter is None:
            run.pieces = [(g.text, [g.index]) for g in run_glyphs]
        else:
            for is_at, seg in _segments(run_glyphs, actual_text == BYPASS):
                if is_at:
                    run.pieces.extend((g.text, [g.index]) for g in seg)
                else:
                    run.pieces.extend(_convert(res.converter, convs, seg, run, page, issues))
        run.text = "".join(text for text, _ in run.pieces)
        dropped = set(run.glyphs)
        for _, src in run.pieces:
            dropped.difference_update(src)
        for gi in dropped:
            if not glyphs[gi].text.isspace():
                glyphs[gi].unattributed = True
        runs.append(run)
    return runs


def _legacy_char(c: str) -> bool:
    """where 8-bit Devanagari fonts put their glyphs: Latin-1, private use,
    control characters"""
    o = ord(c)
    return 0x80 <= o <= 0xFF or 0xE000 <= o <= 0xF8FF or (o < 0x20 and c not in "\t\n\r")


def _suggest(convs: Converters, font: str) -> str | None:
    """the longest converter name inside the font's name (DVB-TTYogesh -> yogesh)"""
    key = font_lookup_key(strip_subset(font))
    found = [n for n in convs.fontconv.converters
             if not is_glyphs_converter(n) and len(n) >= 4 and font_lookup_key(n) in key]
    return max(found, key=lambda n: (len(n), n), default=None)


def report_no_converter(convs: Converters, runs: list[tuple[int, Run]], issues: IssueBag) -> None:
    """(page, run) pairs -> a font with no converter whose text looks like a
    legacy 8-bit encoding
    (UP-CLI-2). Fonts with plain ASCII text (English, or a legacy font that
    uses only ASCII codes) cannot be told apart and are not reported."""
    counts: dict[str, list[int]] = {}
    pages: dict[str, set[int]] = {}
    for page, run in runs:
        if run.converter is not None or run.rule != RULE_NONE or run.logical:
            continue
        c = counts.setdefault(run.font, [0, 0])
        for ch in run.raw:
            if not ch.isspace():
                c[0] += 1
                c[1] += _legacy_char(ch)
        pages.setdefault(run.font, set()).add(page)
    for font, (total, legacy) in counts.items():
        if total and legacy / total >= LEGACY_SHARE:
            suggest = _suggest(convs, font)
            hint = f" ({suggest} may read it: --font-map '{strip_subset(font)}={suggest}')" \
                if suggest else ""
            issues.add(severity="warning", code=NO_CONVERTER, font=font,
                       message=f"{font} has no converter and {legacy} of its {total} "
                               f"characters look like a legacy encoding{hint}",
                       context={"characters": total, "legacy": legacy, "suggest": suggest,
                                "pages": sorted(pages[font])})
