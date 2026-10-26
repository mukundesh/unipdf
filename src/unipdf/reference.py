"""The reference pipeline R (REQUIREMENTS §7.2): indic2unicode as read_pdf.py
uses it, with its two converter-choice bugs fixed by using convert.resolve.

    PyMuPDF open -> ToUnicodeFixer.fix_document -> get_text("dict") ->
    per line, consecutive spans of the same font joined into a run ->
    converter chosen by ConverterResolver -> FontConv.to_unicode ->
    runs concatenated, lines joined with "\\n", blocks with "\\n\\n".

R is the oracle unipdf's own pipeline is checked against, so it depends on
nothing in unipdf except the absorbed converters and the resolver, and it is
kept as plain as read_pdf.py. Differences from read_pdf.py, all deliberate:
- converter choice is ConverterResolver (no *_glyphs on unrepaired fonts, no
  prefix matching, no lossy converter on a font whose map repair found sound),
  with legacy 8-bit fonts read as R reads them (`legacy="keep"`, D-19);
- a page whose blocks give only whitespace is not replaced by page.get_text();
- the PDF is opened once.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import pymupdf

from unipdf.convert.resolve import ConverterResolver
from unipdf.i2u.fix_tounicode import ToUnicodeFixer
from unipdf.i2u.fontconv import FontConv

logger = logging.getLogger(__name__)

PAGE_BREAK = "\n\n--- Page Break ---\n\n"


@dataclass
class RefRun:
    font: str
    converter: str | None
    rule: int | str
    raw: str
    text: str
    error: str | None = None


@dataclass
class RefLine:
    runs: list[RefRun] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


@dataclass
class RefPage:
    number: int  # 0-based
    blocks: list[list[RefLine]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join("\n".join(line.text for line in block) for block in self.blocks)


@dataclass
class RefDocument:
    path: str
    # None when repair was not run (or failed)
    repaired: dict[str, str] | None
    pages: list[RefPage]

    def text(self) -> str:
        return PAGE_BREAK.join(page.text for page in self.pages)

    def to_dict(self) -> dict:
        return asdict(self)


def font_runs(line: dict) -> list[tuple[str, str]]:
    """consecutive non-empty spans of the same font, joined (as read_pdf.py)"""
    runs: list[tuple[str, str]] = []
    for span in line.get("spans", []):
        text, font = span.get("text", ""), span.get("font", "")
        if not text:
            continue
        if runs and runs[-1][0] == font:
            runs[-1] = (font, runs[-1][1] + text)
        else:
            runs.append((font, text))
    return runs


def read_reference(
    path: str,
    pages: list[int] | None = None,
    repair: bool = True,
    force: str | None = None,
    font_map: dict[str, str] | None = None,
) -> RefDocument:
    """R over the 0-based `pages` (all when None). As in read_pdf.py, only the
    selected pages are fed to the converters, in page order, so a stateful
    converter (sakal) starts the first selected page in its initial state."""
    doc = pymupdf.open(path)
    try:
        repaired: dict[str, str] | None = None
        if repair:
            fixer = ToUnicodeFixer()
            try:
                fixer.fix_document(doc)
                repaired = dict(fixer.fixed_font_names)
            except Exception as e:  # noqa: BLE001 - read_pdf.py goes on unrepaired
                logger.warning("ToUnicode repair failed, continuing unrepaired: %s", e)

        # one FontConv per document: converters keep state between runs (sakal)
        fontconv = FontConv()
        resolver = ConverterResolver(fontconv.converters, force=force, font_map=font_map,
                                     legacy="keep")
        selected = range(doc.page_count) if pages is None else \
            [p for p in pages if 0 <= p < doc.page_count]

        out_pages = []
        for pno in selected:
            page = RefPage(pno)
            for block in doc[pno].get_text("dict")["blocks"]:
                if "lines" not in block:
                    continue
                ref_block = []
                for line in block["lines"]:
                    ref_line = RefLine()
                    for font, raw in font_runs(line):
                        res = resolver.resolve(font, repaired)
                        text, error = raw, None
                        if res.converter is not None:
                            try:
                                text = fontconv.to_unicode(res.converter, raw)
                            except Exception as e:  # noqa: BLE001 - UP-CV-5: the raw text stands
                                error = f"{type(e).__name__}: {e}"
                        ref_line.runs.append(RefRun(font, res.converter, res.rule, raw, text, error))
                    ref_block.append(ref_line)
                page.blocks.append(ref_block)
            out_pages.append(page)
        return RefDocument(path, repaired, out_pages)
    finally:
        doc.close()
