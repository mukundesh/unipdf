"""Page overlays for checking geometry by eye (UP-CLI-3).

After cidpdf's visualize_pdf: the page image with word boxes (and cluster
boxes) over it. HTML output puts each word's text, raw text, font, size and
bold/italic in a hover title, since the browser shapes Devanagari and an
image library may not. PNG output draws the boxes only.

Colours: word blue, joined word green, bold word red, cluster orange,
unattributed glyph magenta, legacy region (D-19) grey.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

import pymupdf

from unipdf.model import Document, Page, Word

WORD, JOINED, BOLD, CLUSTER, DROPPED = "#1f5fd1", "#1a9a3a", "#d12a1f", "#e08a00", "#c000c0"
LEGACY = "#707070"


def _word_colour(w: Word) -> str:
    if getattr(w, "bold", False):
        return BOLD
    return JOINED if w.joined_from else WORD


def _word_title(w: Word) -> str:
    parts = [w.text, f"raw: {w.raw_text!r}", f"fonts: {', '.join(w.fonts)}", f"size: {w.size}"]
    for attr in ("bold", "italic"):
        if getattr(w, attr, None) is not None:
            evidence = getattr(w, f"{attr}_evidence", None) or []
            parts.append(f"{attr}: {getattr(w, attr)} {' '.join(evidence)}".rstrip())
    if w.joined_from:
        parts.append(f"joined: {' + '.join(w.joined_from)} ({', '.join(w.join_rules or [])})")
    if w.clusters:
        parts.append("clusters: " + " · ".join(c.text for c in w.clusters))
    return "\n".join(parts)


def _boxes(page: Page, clusters: bool):
    """(bbox, colour, width, title) to draw"""
    for r in page.legacy_regions:
        if r.bbox is not None:
            yield r.bbox, LEGACY, 1.5, (f"8bit:{r.index + 1}, {len(r.words)} words\n"
                                        f"fonts: {', '.join(r.fonts)}\nraw: {r.raw_text!r}")
    for w in page.words:
        if w.region is not None:
            continue
        if w.bbox is not None:
            yield w.bbox, _word_colour(w), 1.0, _word_title(w)
        if clusters and w.clusters:
            for c in w.clusters:
                if c.bbox is not None:
                    yield c.bbox, CLUSTER, 0.5, c.text
        for gi in w.unattributed:
            yield page.glyphs[gi].bbox, DROPPED, 0.8, f"unattributed {page.glyphs[gi].text!r}"


def page_png(pdf: pymupdf.Document, page: Page, zoom: float = 2.0, clusters: bool = False,
             clip: tuple[float, float, float, float] | None = None) -> bytes:
    """the page with its boxes drawn, as PNG"""
    tmp = pymupdf.open()
    tmp.insert_pdf(pdf, from_page=page.index, to_page=page.index)
    p = tmp[0]
    derot = p.derotation_matrix
    for bbox, colour, width, _ in _boxes(page, clusters):
        rgb = tuple(int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        p.draw_rect(pymupdf.Rect(bbox) * derot, color=rgb, width=width * 0.5)
    pix = p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom),
                       clip=pymupdf.Rect(clip) if clip else None)
    return pix.tobytes("png")


def _page_html(pdf: pymupdf.Document, page: Page, zoom: float, clusters: bool) -> str:
    pix = pdf[page.index].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img = base64.b64encode(pix.tobytes("png")).decode()
    rects = []
    for (x0, y0, x1, y1), colour, width, title in _boxes(page, clusters):
        rects.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
            f'stroke="{colour}" stroke-width="{width * 0.6:.2f}"><title>{html.escape(title)}'
            f"</title></rect>"
        )
    return (
        f'<section><h2>Page {page.index + 1}</h2>'
        f'<div class="page" style="width:{page.width * zoom:.0f}px">'
        f'<img src="data:image/png;base64,{img}" alt="page {page.index + 1}">'
        f'<svg viewBox="0 0 {page.width:.2f} {page.height:.2f}">{"".join(rects)}</svg>'
        f"</div></section>"
    )


def write_html(doc: Document, pdf_path: str, out: str, zoom: float = 1.5,
               clusters: bool = True) -> None:
    pdf = pymupdf.open(pdf_path)
    try:
        body = "".join(_page_html(pdf, page, zoom, clusters) for page in doc.pages)
    finally:
        pdf.close()
    name = html.escape(Path(pdf_path).name)
    Path(out).write_text(
        f"""<!doctype html>
<html lang="hi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>unipdf show</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; background: #f4f4f4; color: #111; }}
.page {{ position: relative; background: #fff; box-shadow: 0 1px 4px #0003; }}
.page img {{ display: block; width: 100%; }}
.page svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
.page rect {{ fill: transparent; }}
.page rect:hover {{ fill: #ffe60055; }}
.key span {{ display: inline-block; margin-right: 12px; }}
</style></head><body>
<h1>{name}</h1>
<p class="key"><span style="color:{WORD}">■ word</span><span style="color:{JOINED}">■ joined</span>
<span style="color:{BOLD}">■ bold</span><span style="color:{CLUSTER}">■ cluster</span>
<span style="color:{DROPPED}">■ unattributed glyph</span>
<span style="color:{LEGACY}">■ legacy 8-bit region</span> · hover a box for its text</p>
{body}
</body></html>
""",
        encoding="utf-8",
    )


def write_png(doc: Document, pdf_path: str, out: str, zoom: float = 2.0,
              clusters: bool = False) -> list[str]:
    """one PNG per page: out itself for one page, else out-<page>.png"""
    pdf = pymupdf.open(pdf_path)
    written = []
    try:
        base = Path(out)
        for page in doc.pages:
            path = base if len(doc.pages) == 1 else \
                base.with_name(f"{base.stem}-{page.index + 1}{base.suffix}")
            path.write_bytes(page_png(pdf, page, zoom, clusters))
            written.append(str(path))
    finally:
        pdf.close()
    return written
