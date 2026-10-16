"""unipdf command line.

`unipdf text` gives the text as visual rows with split words joined.
`--rawdict-lines --no-join --convert-actual-text` gives R's text byte for byte
(UP-VF-4a).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """'1,3-5' -> 0-based [0, 2, 3, 4]; pages past the end are ignored"""
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start, end = max(1, int(start_s)), min(page_count, int(end_s))
                pages.update(range(start - 1, end))
            else:
                p = int(part)
                if 1 <= p <= page_count:
                    pages.add(p - 1)
        except ValueError:
            raise ValueError(f"invalid page range: {part!r}") from None
    return sorted(pages)


def parse_font_map(items: list[str] | None) -> dict[str, str]:
    out = {}
    for item in items or []:
        name, sep, conv = item.rpartition("=")
        if not sep or not name or not conv:
            raise ValueError(f"--font-map wants FONT=CONVERTER, got {item!r}")
        out[name] = conv
    return out


def write_output(text: str, path: str | None) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return
    try:
        print(text)
        sys.stdout.flush()
    except BrokenPipeError:
        # e.g. piped into head: silence the flush Python retries at exit
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def cmd_text(args) -> int:
    import pymupdf

    from unipdf.pipeline import read_document

    pages = None
    if args.pages:
        with pymupdf.open(args.pdf) as doc:
            pages = parse_page_range(args.pages, doc.page_count)
    doc = read_document(
        args.pdf,
        pages=pages,
        repair=not args.no_repair,
        force=args.font,
        font_map=parse_font_map(args.font_map),
        join=not args.no_join,
        rawdict_lines=args.rawdict_lines,
        j2=args.j2,
        actual_text="convert" if args.convert_actual_text else "bypass",
    )
    write_output(doc.text(), args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="unipdf", description="Hindi and Marathi text from PDFs as Unicode")
    ap.add_argument("-v", "--verbose", action="store_true", help="log converter and repair messages")
    sub = ap.add_subparsers(dest="command", required=True)

    t = sub.add_parser("text", help="the Unicode text of a PDF")
    t.add_argument("pdf")
    t.add_argument("-p", "--pages", help="pages, e.g. '1', '1-5', '1,3,7-10'")
    t.add_argument("-o", "--output", help="output file (default: stdout)")
    t.add_argument("--no-repair", action="store_true", help="do not repair ToUnicode maps")
    t.add_argument("--font", help="use this converter for every font")
    t.add_argument("--font-map", action="append", metavar="FONT=CONVERTER",
                   help="use CONVERTER for FONT (repeatable), e.g. DVB-TTSurekh=surekh")
    t.add_argument("--rawdict-lines", action="store_true",
                   help="one output line per PyMuPDF line, no visual rows (the R layout)")
    t.add_argument("--no-join", action="store_true", help="do not join split words")
    t.add_argument("--j2", type=float, metavar="RATIO",
                   help="also join words across a generated space narrower than RATIO x "
                        "font size (off by default; e.g. 0.15)")
    t.add_argument("--convert-actual-text", action="store_true",
                   help="run converters over /ActualText too, as R does (D-18)")
    t.set_defaults(fn=cmd_text)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.CRITICAL,
                        format="%(name)s: %(levelname)s %(message)s")
    if not os.path.exists(args.pdf):
        print(f"unipdf: no such file: {args.pdf}", file=sys.stderr)
        return 1
    try:
        return args.fn(args)
    except ValueError as e:
        print(f"unipdf: {e}", file=sys.stderr)
        return 1
