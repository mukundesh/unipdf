"""unipdf command line.

`unipdf text` gives the text as visual rows with split words joined.
`unipdf show` draws word and akshara boxes over the page images.
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


def read(args):
    import pymupdf

    from unipdf.pipeline import read_document

    pages = None
    if args.pages:
        with pymupdf.open(args.pdf) as doc:
            pages = parse_page_range(args.pages, doc.page_count)
    return read_document(
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


def cmd_text(args) -> int:
    write_output(read(args).text(), args.output)
    return 0


def fonts_table(doc) -> str:
    """UP-CLI-1 `fonts`: one row per font name, as tab-separated values"""
    head = ["font", "converter", "rule", "repaired_as", "programs", "bold", "bold_evidence",
            "italic", "italic_evidence"]
    rows = ["\t".join(head)]
    for f in sorted(doc.fonts, key=lambda f: f.name):
        progs = " ".join(
            f"{p.xref}:{p.type}:{p.encoding or '-'}:{'emb' if p.embedded else 'ext'}"
            f"{':tu' if p.has_tounicode else ''}" for p in f.programs) or "-"
        rows.append("\t".join(str(v) for v in [
            f.name, f.converter or "-", f.rule, f.repaired_as or "-", progs,
            f.bold, "; ".join(f.bold_evidence) or "-", f.italic,
            "; ".join(f.italic_evidence) or "-"]))
    return "\n".join(rows)


def cmd_fonts(args) -> int:
    write_output(fonts_table(read(args)), args.output)
    return 0


def cmd_show(args) -> int:
    from pathlib import Path

    from unipdf import show

    out = args.output or str(Path(args.pdf).with_suffix(".show.html").name)
    doc = read(args)
    if out.lower().endswith(".png"):
        written = show.write_png(doc, args.pdf, out, zoom=args.zoom or 2.0,
                                 clusters=args.clusters)
    else:
        show.write_html(doc, args.pdf, out, zoom=args.zoom or 1.5, clusters=args.clusters)
        written = [out]
    for path in written:
        print(path, file=sys.stderr)
    return 0


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("pdf")
    p.add_argument("-p", "--pages", help="pages, e.g. '1', '1-5', '1,3,7-10'")
    p.add_argument("--no-repair", action="store_true", help="do not repair ToUnicode maps")
    p.add_argument("--font", help="use this converter for every font")
    p.add_argument("--font-map", action="append", metavar="FONT=CONVERTER",
                   help="use CONVERTER for FONT (repeatable), e.g. DVB-TTSurekh=surekh")
    p.add_argument("--rawdict-lines", action="store_true",
                   help="one output line per PyMuPDF line, no visual rows (the R layout)")
    p.add_argument("--no-join", action="store_true", help="do not join split words")
    p.add_argument("--j2", type=float, metavar="RATIO",
                   help="also join words across a generated space narrower than RATIO x "
                        "font size (off by default; e.g. 0.15)")
    p.add_argument("--convert-actual-text", action="store_true",
                   help="run converters over /ActualText too, as R does (D-18)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="unipdf", description="Hindi and Marathi text from PDFs as Unicode")
    ap.add_argument("-v", "--verbose", action="store_true", help="log converter and repair messages")
    sub = ap.add_subparsers(dest="command", required=True)

    t = sub.add_parser("text", help="the Unicode text of a PDF")
    add_common(t)
    t.add_argument("-o", "--output", help="output file (default: stdout)")
    t.set_defaults(fn=cmd_text)

    f = sub.add_parser("fonts", help="font table: converter, resolution rule, bold, italic")
    add_common(f)
    f.add_argument("-o", "--output", help="output file (default: stdout)")
    f.set_defaults(fn=cmd_fonts)

    s = sub.add_parser("show", help="page images with word boxes, to check geometry")
    add_common(s)
    s.add_argument("-o", "--output",
                   help="output .html (default: <pdf name>.show.html here) or .png "
                        "(one per page: name-<page>.png)")
    s.add_argument("--clusters", action=argparse.BooleanOptionalAction, default=True,
                   help="draw akshara boxes too (default: yes)")
    s.add_argument("--zoom", type=float, help="image scale (default 1.5 for HTML, 2 for PNG)")
    s.set_defaults(fn=cmd_show)
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
