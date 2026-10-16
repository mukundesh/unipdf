"""Bold and italic per glyph, font run and word (UP-AT-1..5).

Font evidence comes from the font record (pdf/fonts.py). Glyph evidence comes
from how the glyph was drawn (UP-EX-3, SPIKES §1.5):

- `fill_then_stroke(w em)`: the span is filled and then stroked again. This is
  Word's synthetic bold, a stroke of size / 35 (0.029 em);
- `render_mode_2` (fill and stroke at once), `render_mode_1` (stroke only);
- `overprinted`: the span is filled again at the same place.

A stroke thinner than STROKE_MIN em is reported as `thin_stroke` and is not
bold. Glyph evidence makes a font run bold when at least half of its glyphs
carry it; otherwise it is listed with a count. A word is bold if any of its
font runs is (cidpdf's rule). No attribute changes text (UP-AT-5).
"""

from __future__ import annotations

from collections import Counter

from unipdf.model import Font, FontRun, Glyph, union

STROKE_MIN = 0.01  # em


def glyph_bold_evidence(g: Glyph) -> list[str]:
    ev = []
    stroked = g.render_mode in (1, 2) or any(t in (1, 2) for t in g.repeats)
    thin = stroked and g.line_width is not None and g.line_width < STROKE_MIN * g.size
    width = f"({g.line_width / g.size:.3f} em)" if g.line_width is not None else ""
    if thin:
        ev.append(f"thin_stroke{width}")
    elif g.render_mode in (1, 2):
        ev.append(f"render_mode_{g.render_mode}")
    elif any(t in (1, 2) for t in g.repeats):
        ev.append(f"fill_then_stroke{width}")
    if 0 in g.repeats:
        ev.append("overprinted")
    return ev


def _counts_as_bold(evidence: str) -> bool:
    return not evidence.startswith("thin_stroke")


def font_run(font_name: str, font: Font | None, glyphs: list[Glyph], text: str) -> FontRun:
    ink = [g for g in glyphs if not g.synthetic and not g.text.isspace()]
    sizes = Counter(g.size for g in ink)
    run = FontRun(
        font=font_name, text=text, raw_text="".join(g.text for g in glyphs),
        bbox=union(g.bbox for g in ink), glyphs=[g.index for g in glyphs],
        size=sizes.most_common(1)[0][0] if sizes else None,
    )
    if font is not None:
        run.bold, run.bold_evidence = font.bold, list(font.bold_evidence)
        run.italic, run.italic_evidence = font.italic, list(font.italic_evidence)
    # counted by kind: the width in a stroke's evidence differs with size
    kinds: Counter = Counter()
    shown: dict[str, Counter] = {}
    for g in ink:
        for e in dict.fromkeys(glyph_bold_evidence(g)):
            kind = e.split("(")[0]
            kinds[kind] += 1
            shown.setdefault(kind, Counter())[e] += 1
    for kind, k in kinds.items():
        e = shown[kind].most_common(1)[0][0]
        if 2 * k >= len(ink) and _counts_as_bold(e):
            run.bold = True
            run.bold_evidence.append(e)
        else:
            run.bold_evidence.append(f"{e} ({k} of {len(ink)} glyphs)")
    return run


def word_attributes(runs: list[FontRun]) -> tuple[bool, list[str], bool, list[str]]:
    bold = any(r.bold for r in runs)
    italic = any(r.italic for r in runs)
    bold_ev = list(dict.fromkeys(e for r in runs for e in r.bold_evidence))
    italic_ev = list(dict.fromkeys(e for r in runs for e in r.italic_evidence))
    return bold, bold_ev, italic, italic_ev
