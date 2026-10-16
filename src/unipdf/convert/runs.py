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
    RULE_REPAIRED,
    SOUND_MAP,
    ConverterResolver,
    Resolution,
    strip_subset,
)
from unipdf.i2u.fontconv import FontConv
from unipdf.issues import CONVERTER_ERROR, PROVENANCE_UNAVAILABLE, UNCONVERTED_CHAR, IssueBag
from unipdf.model import Font, Glyph, Run
from unipdf.pdf.glyphs import RawLine

BYPASS, CONVERT = "bypass", "convert"


class Converters:
    """The converters of one document, and the decision for each font name."""

    def __init__(
        self,
        repaired: Mapping[str, str] | None,
        force: str | None = None,
        font_map: Mapping[str, str] | None = None,
    ):
        self.fontconv = FontConv()
        self.resolver = ConverterResolver(self.fontconv.converters, force=force,
                                          font_map=font_map)
        self.repaired = repaired
        self.resolutions: dict[str, Resolution] = {}
        self._run_level_reported: set[str] = set()

    def resolve(self, font: str) -> Resolution:
        res = self.resolutions.get(font)
        if res is None:
            res = self.resolutions[font] = self.resolver.resolve(font, self.repaired)
        return res

    def fonts(self) -> list[Font]:
        out = []
        for name, res in self.resolutions.items():
            repaired_as = None
            if self.repaired is not None:
                repaired_as = self.repaired.get(strip_subset(name))
            out.append(Font(name, res.converter, res.rule, res.matched,
                            repaired_as is not None, repaired_as))
        return out


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
