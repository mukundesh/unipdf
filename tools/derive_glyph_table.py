"""Derive a glyph table for indic2unicode's fix_tounicode from PDFs whose
subsets of a font keep a GSUB.

Some producers (Acrobat Distiller through a printer driver) carry a font as
bare outlines, with no cmap, no names and no GSUB, so fix_tounicode has
nothing to read its glyphs from. Word carries the same font version with its
GSUB, and fix_tounicode already spells every glyph out of that. This reads
those spellings over many PDFs, keeps the subsets of one glyph count, checks
that they agree, and prints the table as Python, to paste into
fix_tounicode.py:

    uv run python tools/derive_glyph_table.py Mangal 885 DIR [DIR ...]

A glyph the subsets spell more than one way is printed with all its readings
in a comment, for a person to decide.
"""

from __future__ import annotations

import argparse
import collections
import logging
import sys
from pathlib import Path

import pymupdf

from unipdf.i2u.fix_tounicode import ToUnicodeFixer, font_lookup_key


def spellings(paths, family: str, count: int):
    key = font_lookup_key(family)
    seen: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    subsets = 0
    for path in paths:
        try:
            doc = pymupdf.open(path)
        except Exception as e:  # noqa: BLE001 - a file that does not open is skipped
            print(f"# skipped {path.name}: {e}", file=sys.stderr)
            continue
        fixer = ToUnicodeFixer()
        fonts = {}
        for pno in range(doc.page_count):
            for x in doc.get_page_fonts(pno):
                if x[2] == "Type0" and font_lookup_key(fixer.base_font(x[3])) == key:
                    fonts[x[0]] = x[3]
        for xref in fonts:
            if fixer.glyph_count(doc, xref) != count:
                continue
            font = fixer.open_font(doc, xref)
            if font is None or "GSUB" not in font:
                continue
            subsets += 1
            for gid, ustr in fixer.glyph_strings(doc, xref).items():
                seen[gid][ustr] += 1
    return seen, subsets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("family", help="font name, e.g. Mangal (its weights are matched too)")
    ap.add_argument("count", type=int, help="glyph count of the numbering")
    ap.add_argument("dirs", nargs="+", type=Path, help="directories of PDFs")
    args = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    paths = sorted(p for d in args.dirs for p in d.glob("*.pdf"))
    seen, subsets = spellings(paths, args.family, args.count)
    print(f"# {len(seen)} glyphs from {subsets} subsets of {args.family} ({args.count} glyphs)")
    items = []
    for gid in sorted(seen):
        readings = seen[gid].most_common()
        note = "" if len(readings) == 1 else "  # " + ", ".join(f"{s!r}: {n}" for s, n in readings)
        items.append((gid, readings[0][0], note))
    print("{")
    line = "   "
    for gid, ustr, note in items:
        cell = f" {gid}: {ustr!r},"
        if note:
            print(line) if line.strip() else None
            print(f"   {cell}{note}")
            line = "   "
        elif len(line) + len(cell) > 76:
            print(line)
            line = "   " + cell
        else:
            line += cell
    if line.strip():
        print(line)
    print("}")
    return 0 if seen else 1


if __name__ == "__main__":
    sys.exit(main())
