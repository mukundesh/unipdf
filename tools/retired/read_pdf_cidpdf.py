#!/usr/bin/env python3
from __future__ import annotations

"""
read_pdf_cidpdf.py - Read and convert Indian language text from PDFs to Unicode
using the cidpdf library.

This is the cidpdf counterpart of read_pdf.py. Where read_pdf.py repairs the
ToUnicode maps with indic2unicode and extracts text with PyMuPDF, cidpdf reads
the CIDs of every glyph through its custom pypdfium2 build and converts them
with the per-font YAML CMaps in cidpdf/src/cidpdf/cmaps. Since it works glyph
by glyph, it also gives word bounding boxes.

cidpdf needs Python >= 3.12 and its patched pypdfium2, so run this with the
cidpdf virtualenv:

Usage:
    cidpdf/.venv/bin/python read_pdf_cidpdf.py input.pdf
    cidpdf/.venv/bin/python read_pdf_cidpdf.py -p 1,3-5 input.pdf -o output.txt
    cidpdf/.venv/bin/python read_pdf_cidpdf.py --words input.pdf
    cidpdf/.venv/bin/python read_pdf_cidpdf.py --words --format json input.pdf
"""

import argparse
import json
import os
import sys
from collections import Counter

# Prefer the cidpdf source tree next to this script over an installed copy
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CIDPDF_SRC = os.path.join(BASE_DIR, "cidpdf", "src")
if os.path.isdir(CIDPDF_SRC) and CIDPDF_SRC not in sys.path:
    sys.path.insert(0, CIDPDF_SRC)

try:
    from cidpdf.cid_pdf import CidPdfDocument, CidPdfOptions, CidPdfParser
except ImportError as e:
    print(
        f"Error importing cidpdf: {e}\n"
        "cidpdf needs Python >= 3.12 and its patched pypdfium2. Run this script\n"
        "with the cidpdf virtualenv: cidpdf/.venv/bin/python read_pdf_cidpdf.py ...",
        file=sys.stderr,
    )
    sys.exit(1)


PAGE_BREAK = "\n\n--- Page Break ---\n\n"

# Issue codes worth telling the user about: text in these fonts or CIDs is
# missing from the output rather than wrong in it
REPORTED_ISSUES = {
    "missing_cmap_file": "fonts with no CMap file",
    "missing_cmap_entry": "CIDs missing from their font's CMap",
    "invalid_cmap_file": "CMap files that could not be read",
}


def parse_page_range(range_str: str, max_pages: int) -> list[int]:
    """Parse comma-separated page ranges like '1,3-5' into 0-indexed page indices."""
    pages = set()
    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start = max(1, int(start_s))
                end = min(max_pages, int(end_s))
                pages.update(p - 1 for p in range(start, end + 1))
            else:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
        except ValueError:
            raise ValueError(f"Invalid page range: {part!r}") from None
    return sorted(pages)


def parse_pdf(
    pdf_path: str,
    cmaps_dir: str | None = None,
    placeholder: str = "empty",
    layout_engine: str = "pypdfium2",
) -> CidPdfDocument:
    """Parse a PDF with cidpdf. cidpdf always parses every page."""
    parser = CidPdfParser(cmaps_dir=cmaps_dir)
    return parser.parse_file(
        pdf_path,
        options=CidPdfOptions(
            # fonts are needed for the font names and versions that pick a CMap
            extract_fonts=True,
            render_glyphs=False,
            collect_reports=False,
            unicode_placeholder_mode=placeholder,
            layout_engine=layout_engine,
        ),
    )


def select_pages(doc: CidPdfDocument, page_numbers: list[int] | None):
    if page_numbers is None:
        return list(doc.pages)
    wanted = set(page_numbers)
    return [page for page in doc.pages if page.page_index in wanted]


def report_issues(doc: CidPdfDocument, page_numbers: list[int] | None) -> None:
    """Summarise on stderr the issues that leave text out of the output."""
    wanted = None if page_numbers is None else set(page_numbers)
    counts: Counter[str] = Counter()
    fonts: dict[str, set[str]] = {}
    for issue in doc.issues.all():
        if issue.code not in REPORTED_ISSUES:
            continue
        if wanted is not None and issue.page_index is not None:
            if issue.page_index not in wanted:
                continue
        counts[issue.code] += 1
        if issue.font_id:
            fonts.setdefault(issue.code, set()).add(issue.font_id)
    for code, count in counts.items():
        detail = ", ".join(sorted(fonts.get(code, ())))
        print(
            f"Warning: {count} {REPORTED_ISSUES[code]} ({code})"
            + (f": {detail}" if detail else ""),
            file=sys.stderr,
        )


def bbox_points(bbox, page_height: float | None) -> tuple[float, ...] | None:
    """cidpdf bbox (x, y, w, h scaled by scale_factor, bottom-left origin)
    -> (x0, y0, x1, y1) in PDF points with a top-left origin, as PyMuPDF uses."""
    if bbox is None:
        return None
    s = bbox.scale_factor or 1
    x0, x1 = bbox.x / s, (bbox.x + bbox.w) / s
    bottom, top = bbox.y / s, (bbox.y + bbox.h) / s
    if bbox.coord_origin == "bottom_left" and page_height is not None:
        y0, y1 = page_height - top, page_height - bottom
    else:
        y0, y1 = bottom, top
    return tuple(round(v, 2) for v in (x0, y0, x1, y1))


def pages_to_text(doc: CidPdfDocument, page_numbers: list[int] | None = None) -> str:
    """The Unicode text of the selected pages, one visual line per line."""
    results = []
    for page in select_pages(doc, page_numbers):
        results.append("\n".join(line.text for line in page.lines))
    return PAGE_BREAK.join(results)


def pages_to_words(
    doc: CidPdfDocument, page_numbers: list[int] | None = None
) -> list[dict]:
    """One record per word: 1-based page, line and word indices, bbox, font, text."""
    font_names = {font.id: font.raw_pdf_name for font in doc.fonts}
    records = []
    for page in select_pages(doc, page_numbers):
        for word in page.words:
            records.append(
                {
                    "page": page.page_index + 1,
                    "line": None if word.line_index is None else word.line_index + 1,
                    "word": word.word_index + 1,
                    "bbox": bbox_points(word.bbox, page.height),
                    "font": font_names.get(word.font_id, word.font_id),
                    "font_size": word.font_size,
                    "bold": word.is_bold,
                    "text": word.text,
                }
            )
    return records


def format_words_tsv(records: list[dict]) -> str:
    rows = ["page\tline\tword\tx0\ty0\tx1\ty1\tfont\ttext"]
    for r in records:
        bbox = r["bbox"] or ("", "", "", "")
        line = "" if r["line"] is None else r["line"]
        text = r["text"].replace("\t", "\\t").replace("\n", "\\n")
        rows.append(
            f"{r['page']}\t{line}\t{r['word']}\t"
            + "\t".join(f"{v:g}" if v != "" else "" for v in bbox)
            + f"\t{r['font']}\t{text}"
        )
    return "\n".join(rows)


def read_pdf_to_unicode(
    pdf_path: str,
    page_numbers: list[int] | None = None,
    cmaps_dir: str | None = None,
) -> str:
    """
    Read a PDF file and return its content converted to Unicode.

    Args:
        pdf_path: Path to the input PDF file.
        page_numbers: List of 0-indexed page numbers to convert (None converts all).
        cmaps_dir: Directory of cidpdf YAML CMaps (default: the bundled ones).

    Returns:
        Converted Unicode text.
    """
    doc = parse_pdf(pdf_path, cmaps_dir=cmaps_dir)
    return pages_to_text(doc, page_numbers)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and convert Indian language text from PDFs to "
        "Unicode using cidpdf."
    )
    parser.add_argument("pdf_file", help="Path to input PDF file")
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        default=None,
        help="Path to output file (default: stdout)",
    )
    parser.add_argument(
        "-p",
        "--pages",
        dest="pages",
        default=None,
        help="Page numbers or ranges to process (e.g. '1', '1-5', '1,3,7-10')",
    )
    parser.add_argument(
        "-w",
        "--words",
        action="store_true",
        help="Output words with bounding boxes instead of plain text",
    )
    parser.add_argument(
        "--format",
        choices=["tsv", "json"],
        default="tsv",
        help="Output format for --words (default: tsv). Bboxes are in PDF "
        "points with a top-left origin",
    )
    parser.add_argument(
        "--cmaps-dir",
        default=None,
        help="Directory of cidpdf YAML CMaps (default: $CMAPS_DIR or the "
        "bundled cmaps)",
    )
    parser.add_argument(
        "--placeholder",
        choices=["empty", "raw_cids", "replacement_char"],
        default="empty",
        help="What to output for glyphs with no CMap entry (default: empty)",
    )
    parser.add_argument(
        "--layout-engine",
        choices=["pypdfium2", "visual_row"],
        default="pypdfium2",
        help="cidpdf layout engine for line/word grouping (default: pypdfium2)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.pdf_file):
        print(f"Error: File not found: {args.pdf_file}", file=sys.stderr)
        sys.exit(1)

    try:
        doc = parse_pdf(
            args.pdf_file,
            cmaps_dir=args.cmaps_dir,
            placeholder=args.placeholder,
            layout_engine=args.layout_engine,
        )
        page_numbers = None
        if args.pages:
            page_numbers = parse_page_range(args.pages, len(doc.pages))
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    report_issues(doc, page_numbers)

    if args.words:
        records = pages_to_words(doc, page_numbers)
        if args.format == "json":
            output = json.dumps(records, ensure_ascii=False, indent=2)
        else:
            output = format_words_tsv(records)
    else:
        output = pages_to_text(doc, page_numbers)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Successfully converted PDF and saved to {args.output}", file=sys.stderr)
    else:
        try:
            print(output)
            sys.stdout.flush()
        except BrokenPipeError:
            # e.g. piped into head: silence the flush Python retries at exit
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


if __name__ == "__main__":
    main()
