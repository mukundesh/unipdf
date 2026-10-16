#!/usr/bin/env python3
from __future__ import annotations

"""
read_pdf.py - Read and convert Indian language text from PDFs to Unicode.

This script uses the indic2unicode library to:
1. Repair broken or incomplete PDF ToUnicode font maps (via ToUnicodeFixer).
2. Extract text from PDF pages (using PyMuPDF).
3. Convert proprietary/legacy font encodings (Chanakya, Nudi, Vanavil, etc.)
   or reorder visual glyphs from repaired modern fonts (Nirmala UI, Mangal,
   Arial Unicode MS, etc.) into proper Unicode strings.

Usage:
    python read_pdf.py input.pdf
    python read_pdf.py -f chanakya input.pdf -o output.txt
    python read_pdf.py -p 1,3-5 input.pdf
"""

import argparse
import os
import re
import sys

# Ensure indic2unicode library can be imported
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
PKG_DIR = os.path.join(BASE_DIR, "indic2unicode")
if PKG_DIR not in sys.path:
    sys.path.insert(0, PKG_DIR)

try:
    import pymupdf
except ImportError:
    print(
        "Error: 'pymupdf' is required to read PDF files.\n"
        "Please install it with: pip install pymupdf",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from indic2unicode.fontconv import FontConv
except ImportError as e:
    print(
        f"Error importing indic2unicode.fontconv: {e}\n"
        "Ensure requirements are installed: pip install ply",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from indic2unicode.tools.fix_tounicode import ToUnicodeFixer, get_font_converter
    HAS_FIX_TOUNICODE = True
    TOUNICODE_IMPORT_ERROR = None
except ImportError as e:
    HAS_FIX_TOUNICODE = False
    ToUnicodeFixer = None  # type: ignore
    get_font_converter = None  # type: ignore
    TOUNICODE_IMPORT_ERROR = str(e)


def clean_font_name(fontname: str) -> str:
    """Strip PDF font subset prefix (e.g., 'ABCDEF+FontName' -> 'FontName')."""
    if not fontname:
        return ""
    return re.sub(r"^[A-Z]{6}\+", "", fontname)


def resolve_font_converter(fontname: str, font_conv: FontConv) -> str | None:
    """Find the best matching converter in FontConv for a given font name."""
    if not fontname:
        return None

    # Direct match
    if fontname in font_conv.converters:
        return fontname

    clean = clean_font_name(fontname)
    if clean in font_conv.converters:
        return clean

    # Normalized lookup key (ignore spaces, hyphens, underscores, case)
    norm_key = re.sub(r"[\s\-_,]+", "", clean.split(",")[0]).lower()
    for name in font_conv.converters:
        cand_key = re.sub(r"[\s\-_,]+", "", name.split(",")[0]).lower()
        if norm_key == cand_key:
            return name

    # Prefix match (e.g. 'VANAVILAvvaiyar' -> 'vanavil')
    for name in font_conv.converters:
        if clean.lower().startswith(name.lower()):
            return name

    return None


def convert_span_text(
    text: str,
    font_name: str,
    font_conv: FontConv,
    fixer: ToUnicodeFixer | None = None,
    explicit_font: str | None = None,
) -> str:
    """Convert a text span to Unicode based on font metadata."""
    if not text:
        return ""

    # If user provided an explicit font, use that converter directly
    if explicit_font:
        try:
            return font_conv.to_unicode(explicit_font, text)
        except Exception:
            return text

    clean_name = clean_font_name(font_name)

    # Check if this font was repaired by ToUnicodeFixer
    if fixer and HAS_FIX_TOUNICODE and get_font_converter is not None:
        repaired_base = fixer.fixed_font_names.get(clean_name, clean_name)
        glyphs_conv = get_font_converter(repaired_base) or get_font_converter(clean_name)
        if glyphs_conv and glyphs_conv in font_conv.converters:
            try:
                return font_conv.to_unicode(glyphs_conv, text)
            except Exception:
                pass

    # Check if font matches a known legacy converter in indic2unicode
    matched_conv = resolve_font_converter(font_name, font_conv)
    if matched_conv:
        try:
            return font_conv.to_unicode(matched_conv, text)
        except Exception:
            pass

    return text


def extract_page_unicode(
    page,
    font_conv: FontConv,
    fixer: ToUnicodeFixer | None = None,
    explicit_font: str | None = None,
) -> str:
    """Extract and convert text of a single PDF page into Unicode."""
    # When an explicit font is specified, convert full page text directly
    if explicit_font:
        raw_text = page.get_text()
        try:
            return font_conv.to_unicode(explicit_font, raw_text)
        except Exception as e:
            print(
                f"Warning: Conversion with font '{explicit_font}' failed: {e}",
                file=sys.stderr,
            )
            return raw_text

    page_dict = page.get_text("dict")
    page_text_blocks = []

    for block in page_dict.get("blocks", []):
        if "lines" not in block:
            continue

        block_lines = []
        for line in block["lines"]:
            # Group consecutive spans with identical font to preserve syllable integrity
            grouped_spans: list[tuple[str, str]] = []
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                span_font = span.get("font", "")
                if not span_text:
                    continue
                if grouped_spans and grouped_spans[-1][0] == span_font:
                    grouped_spans[-1] = (span_font, grouped_spans[-1][1] + span_text)
                else:
                    grouped_spans.append((span_font, span_text))

            line_parts = []
            for sfont, stext in grouped_spans:
                converted = convert_span_text(
                    text=stext,
                    font_name=sfont,
                    font_conv=font_conv,
                    fixer=fixer,
                    explicit_font=explicit_font,
                )
                line_parts.append(converted)

            block_lines.append("".join(line_parts))

        page_text_blocks.append("\n".join(block_lines))

    extracted = "\n\n".join(page_text_blocks)
    # Fallback to plain get_text() if blocks yielded nothing
    if not extracted.strip():
        return page.get_text()
    return extracted


def parse_page_range(range_str: str, max_pages: int) -> list[int]:
    """Parse comma-separated page ranges like '1,3-5' into 0-indexed page indices."""
    pages = set()
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = max(1, int(start_s))
            end = min(max_pages, int(end_s))
            for p in range(start, end + 1):
                pages.add(p - 1)
        else:
            p = int(part)
            if 1 <= p <= max_pages:
                pages.add(p - 1)
    return sorted(pages)


def read_pdf_to_unicode(
    pdf_path: str,
    fontname: str | None = None,
    repair_tounicode: bool = True,
    page_numbers: list[int] | None = None,
) -> str:
    """
    Read a PDF file and return its content converted to Unicode.

    Args:
        pdf_path: Path to the input PDF file.
        fontname: Optional font name override (e.g. 'chanakya', 'nudi', 'vanavil', 'sakal').
        repair_tounicode: Whether to fix PDF font ToUnicode CMaps using ToUnicodeFixer.
        page_numbers: List of 0-indexed page numbers to convert (None converts all).

    Returns:
        Converted Unicode text.
    """
    doc = pymupdf.open(pdf_path)
    font_conv = FontConv()

    fixer = None
    if repair_tounicode:
        if HAS_FIX_TOUNICODE and ToUnicodeFixer is not None:
            try:
                fixer = ToUnicodeFixer()
                num_repaired = fixer.fix_document(doc)
                if num_repaired > 0 and fixer.fixed_fonts:
                    print(
                        f"Repaired {num_repaired} glyphs in fonts: {', '.join(sorted(fixer.fixed_fonts))}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"Warning: Could not repair ToUnicode map: {e}", file=sys.stderr)
                fixer = None
        elif TOUNICODE_IMPORT_ERROR:
            print(
                f"Note: PDF font CMap repair is disabled ({TOUNICODE_IMPORT_ERROR}).\n"
                "If your PDF requires ToUnicode CMap repair, please run: pip install fonttools",
                file=sys.stderr,
            )

    total_pages = doc.page_count
    if page_numbers is None:
        target_pages = range(total_pages)
    else:
        target_pages = [p for p in page_numbers if 0 <= p < total_pages]

    results = []
    for pno in target_pages:
        page = doc.load_page(pno)
        page_text = extract_page_unicode(
            page=page,
            font_conv=font_conv,
            fixer=fixer,
            explicit_font=fontname,
        )
        results.append(page_text)

    doc.close()
    return "\n\n--- Page Break ---\n\n".join(results)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and convert Indian language text from PDFs to Unicode."
    )
    parser.add_argument("pdf_file", help="Path to input PDF file")
    parser.add_argument(
        "-f",
        "--font",
        dest="fontname",
        default=None,
        help="Explicit font converter name (e.g., chanakya, nudi, vanavil, surekh, sakal, etc.)",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        default=None,
        help="Path to output text file (default: stdout)",
    )
    parser.add_argument(
        "-p",
        "--pages",
        dest="pages",
        default=None,
        help="Page numbers or ranges to process (e.g. '1', '1-5', '1,3,7-10')",
    )
    parser.add_argument(
        "--no-repair",
        dest="no_repair",
        action="store_true",
        help="Disable automatic PDF ToUnicode CMap repair",
    )

    args = parser.parse_args()

    if not os.path.exists(args.pdf_file):
        print(f"Error: File not found: {args.pdf_file}", file=sys.stderr)
        sys.exit(1)

    # Determine pages if specified
    doc = pymupdf.open(args.pdf_file)
    max_pages = doc.page_count
    doc.close()

    page_numbers = None
    if args.pages:
        page_numbers = parse_page_range(args.pages, max_pages)

    unicode_text = read_pdf_to_unicode(
        pdf_path=args.pdf_file,
        fontname=args.fontname,
        repair_tounicode=not args.no_repair,
        page_numbers=page_numbers,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(unicode_text)
        print(f"Successfully converted PDF and saved to {args.output}", file=sys.stderr)
    else:
        print(unicode_text)


if __name__ == "__main__":
    main()
