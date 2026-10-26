"""unipdf.open(): PDF -> Document (UP-API-1).

    open -> repair (UP-RP) -> per page: glyphs (UP-EX) -> runs, converted
    in document order (UP-CV) -> visual rows (UP-LY-2) -> words and joins
    (UP-LY-4/5); words in legacy 8-bit fonts -> legacy regions (D-19)

With `rawdict_lines=True, join=False, actual_text="convert", legacy="keep"`
the text is R's byte for byte (UP-VF-4a).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping

import pymupdf

from unipdf.convert.legacy import SKIP
from unipdf.convert.resolve import RULE_REPAIRED
from unipdf.convert.runs import BYPASS, CONVERT, Converters, convert_line, report_no_converter
from unipdf.issues import LEGACY_FONT, NO_TEXT_LAYER, IssueBag
from unipdf.layout.rows import ROW_TOLERANCE, visual_rows
from unipdf.layout.words import layout_page
from unipdf.model import Document, Page
from unipdf.pdf.fonts import read_programs
from unipdf.pdf.glyphs import extract_page
from unipdf.pdf.repair import repair as repair_document

# J2 threshold (gap / font size); None = J2 off. See SPIKES / M2 step 9.
J2_DEFAULT: float | None = None


class PasswordRequired(Exception):
    """the PDF is encrypted and does not open without a password (UP-IN-1)"""


def open_pdf(data: bytes) -> pymupdf.Document:
    """the PDF in `data`; pymupdf.FileDataError if it is not one. pymupdf
    opens what it cannot read as a PDF as some other kind of document - a
    text file, an image - whatever the file type it is told"""
    doc = pymupdf.open(stream=data, filetype="pdf")
    if not doc.is_pdf:
        doc.close()
        raise pymupdf.FileDataError("not a PDF")
    return doc


def read_document(
    source: str | os.PathLike | bytes,
    pages: list[int] | None = None,
    repair: bool = True,
    force: str | None = None,
    font_map: Mapping[str, str] | None = None,
    join: bool = True,
    rawdict_lines: bool = False,
    j2: float | None = J2_DEFAULT,
    actual_text: str = BYPASS,
    row_tolerance: float = ROW_TOLERANCE,
    legacy: str = SKIP,
) -> Document:
    """Read a PDF into a Document: pages, lines, words with boxes, fonts and
    issues (docs/USAGE.md; the JSON form is specs/JSON_SCHEMA.md).

    source         a path, or the PDF's bytes
    pages          0-based page numbers to read, None for all; numbers past
                   the end are ignored. Pages are converted in order, so a
                   converter that keeps state starts afresh on the first one
    repair         repair broken font maps first (default True)
    force          a converter name to use for every font
    font_map       {font name: converter name} for named fonts, matched with
                   or without the subset prefix and style suffix
    join           join words PyMuPDF split before a vowel sign (default True)
    rawdict_lines  one output line per PyMuPDF line instead of visual rows
    j2             also join across a made-up space narrower than j2 x font
                   size (off by default; 0.15 is a reasonable value)
    actual_text    "bypass" (default): use a PDF's ActualText as the text,
                   unless it is known to be wrong; "convert": run converters
                   over it, as the old read_pdf.py did
    row_tolerance  how far apart, in font sizes, two baselines can be and
                   still be one visual row (default 0.2)
    legacy         "skip" (default): leave words in legacy 8-bit fonts out of
                   the text, as legacy regions; "keep": pass them through as
                   the old read_pdf.py did

    Raises FileNotFoundError, pymupdf.FileDataError (not a PDF),
    PasswordRequired (encrypted), ValueError (an unknown converter or
    option value)."""
    if actual_text not in (BYPASS, CONVERT):
        raise ValueError(f"actual_text must be {BYPASS!r} or {CONVERT!r}")
    if isinstance(source, bytes | bytearray):
        data = bytes(source)
        doc = open_pdf(data)
        info = {"filename": None}
    else:
        path = os.fspath(source)
        with open(path, "rb") as f:
            data = f.read()
        doc = open_pdf(data)
        info = {"filename": path}
    info.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))

    try:
        if doc.needs_pass:
            raise PasswordRequired(info["filename"] or "<bytes>")
        issues = IssueBag()
        selected = range(doc.page_count) if pages is None else \
            [p for p in pages if 0 <= p < doc.page_count]
        programs = read_programs(doc, selected)  # before repair rewrites ToUnicode
        repaired = repair_document(doc, issues).repaired if repair else None
        convs = Converters(repaired, force=force, font_map=font_map, programs=programs,
                           legacy=legacy)

        def read_glyphs(font: str, text: str) -> bool:
            """an ActualText group not to use (D-20)"""
            return "\ufffd" in text or convs.resolve(font).rule == RULE_REPAIRED

        out_pages = []
        rotated: dict[int, pymupdf.Matrix] = {}  # page -> unrotated to displayed
        for pno in selected:
            pdf_page = doc[pno]
            pg = extract_page(pdf_page, issues,
                              read_glyphs=None if actual_text == CONVERT else read_glyphs)
            page = Page(pno, pdf_page.rect.width, pdf_page.rect.height, pdf_page.rotation,
                        glyphs=pg.glyphs)
            if not pg.glyphs:
                issues.add(severity="info", code=NO_TEXT_LAYER, page=pno,
                           message="page has no text")
            for line in pg.lines:
                page.runs.extend(convert_line(line, pg.glyphs, convs, pno, issues,
                                              first_index=len(page.runs),
                                              actual_text=actual_text))
            if rawdict_lines:
                rows = [[line] for line in pg.lines]
            else:
                rows = visual_rows(pg.lines, row_tolerance)
            layout_page(page, pg.lines, page.runs, rows, issues, join=join, j2=j2,
                        font_of=convs.font)
            if rawdict_lines:
                page.blocks = list(pg.blocks)
            else:
                page.blocks = list(dict.fromkeys(line.block for line in page.lines))
            if pdf_page.rotation:
                rotated[pno] = pdf_page.rotation_matrix
                to_displayed(page, rotated[pno])
            out_pages.append(page)
        report_no_converter(convs, [(p.index, r) for p in out_pages for r in p.runs], issues)
        for issue in issues.all():
            if issue.page in rotated and issue.bbox is not None:
                issue.bbox = _box(issue.bbox, rotated[issue.page])
        report_legacy(convs, out_pages, issues)

        options = {
            "pages": None if pages is None else list(selected),
            "repair": repair,
            "force": force,
            "font_map": dict(font_map or {}),
            "join": join,
            "rawdict_lines": rawdict_lines,
            "j2": j2,
            "actual_text": actual_text,
            "row_tolerance": row_tolerance,
            "legacy": legacy,
        }
        return Document(source=info, options=options, pages=out_pages, fonts=convs.fonts(),
                        issues=issues.all(), repaired=repaired)
    finally:
        doc.close()


def report_legacy(convs: Converters, pages: list[Page], issues: IssueBag) -> None:
    """one issue per legacy font: how many words were left out (D-19). Word's
    second font object of a font ("DVB-TTYogesh+1") counts with the first"""
    words: dict[str, int] = {}
    regions: dict[str, set[tuple[int, int]]] = {}
    for page in pages:
        for region in page.legacy_regions:
            for wi in region.words:
                for font in {_base(f) for f in page.words[wi].fonts if f in region.fonts}:
                    words[font] = words.get(font, 0) + 1
                    regions.setdefault(font, set()).add((page.index, region.index))
    for font, found in regions.items():
        family = convs.resolve(font).matched
        issues.add(severity="warning", code=LEGACY_FONT, font=font,
                   message=f"{font} is a legacy 8-bit font ({family}): "
                           f"{_count(words[font], 'word')} left out, in "
                           f"{_count(len(found), 'region')}",
                   context={"family": family, "words": words[font], "regions": len(found),
                            "pages": sorted({p for p, _ in found})})


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _base(font: str) -> str:
    return re.sub(r"\+\d+$", "", font)


def _box(b, m: pymupdf.Matrix):
    return None if b is None else tuple(pymupdf.Rect(b) * m)


def to_displayed(page: Page, m: pymupdf.Matrix) -> None:
    """the boxes and points of a rotated page, made in the unrotated page
    where its text runs left to right, put where the page is displayed: the
    space of `page.width` x `page.height` and of the page's image"""
    for g in page.glyphs:
        g.bbox = _box(g.bbox, m)
        g.origin = tuple(pymupdf.Point(g.origin) * m)
    for line in page.lines:
        line.bbox = _box(line.bbox, m)
    for w in page.words:
        w.bbox = _box(w.bbox, m)
        for c in w.clusters or []:
            c.bbox = _box(c.bbox, m)
        for fr in w.font_runs:
            fr.bbox = _box(fr.bbox, m)
    for r in page.legacy_regions:
        r.bbox = _box(r.bbox, m)
