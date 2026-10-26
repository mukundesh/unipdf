"""unipdf command line (UP-CLI-1..3).

`unipdf text` gives the text as visual rows with split words joined.
`unipdf words` / `glyphs` give one row per word / glyph; `json` the model.
`unipdf regions` lists the regions of words in legacy 8-bit fonts, which the
text leaves out (D-19). `unipdf show` draws word and akshara boxes over the
page images. `--rawdict-lines --no-join --convert-actual-text --keep-legacy`
gives R's text byte for byte (UP-VF-4a).

The words and glyphs tables number pages, lines, words and glyphs from 1, as
`-p` does; the JSON model numbers from 0. Text that would be missing from the
output is summarised on stderr (UP-CLI-2). Exit status: 0, with or without
warnings; 1 when the input cannot be read or an option is wrong; 2 for usage
errors (argparse).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict

from unipdf.issues import (
    CONVERTER_ERROR,
    LEGACY_FONT,
    NO_CONVERTER,
    REPAIR_FAILED,
    UNCONVERTED_CHAR,
)


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
    from unipdf.pipeline import open_pdf, read_document

    pages = None
    if args.pages:
        with open(args.pdf, "rb") as f, open_pdf(f.read()) as doc:
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
        legacy="keep" if args.keep_legacy else "skip",
    )


# ---- missing text on stderr (UP-CLI-2)


def summary(doc) -> list[str]:
    """one line per kind of problem that leaves text missing or unconverted"""
    by_code = defaultdict(list)
    for issue in doc.issues:
        by_code[issue.code].append(issue)
    lines = [f"{i.message} ({code})" for code in (LEGACY_FONT, NO_CONVERTER)
             for i in by_code[code]]
    for code, what in (
        (UNCONVERTED_CHAR, "characters had no token in their converter and are missing"),
        (CONVERTER_ERROR, "runs failed to convert and are left as in the PDF"),
    ):
        found = by_code[code]
        if found:
            fonts = ", ".join(sorted({i.font for i in found if i.font}))
            lines.append(f"{len(found)} {what} ({code})" + (f": {fonts}" if fonts else ""))
    lines.extend(f"{i.message} ({REPAIR_FAILED})" for i in by_code[REPAIR_FAILED])
    return lines


def report(doc) -> None:
    for line in summary(doc):
        print(f"unipdf: warning: {line}", file=sys.stderr)


# ---- tables


_ESCAPES = {"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"}


def cell(v) -> str:
    """a TSV cell: tabs, newlines, backslashes and control characters escaped"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{round(v, 2):g}"
    if isinstance(v, list | tuple):
        return " ".join(cell(x) for x in v)
    return "".join(_ESCAPES.get(c) or (f"\\x{ord(c):02x}" if ord(c) < 0x20 or ord(c) == 0x7F
                                       else c) for c in str(v))


def _box(b):
    return None if b is None else [round(v, 2) for v in b]


def word_records(doc) -> list[dict]:
    """UP-CLI-1 `words`: one record per word, numbered from 1"""
    out = []
    for page in doc.pages:
        for w in page.words:
            out.append({
                "page": page.index + 1, "line": w.line + 1, "word": w.index + 1,
                "bbox": _box(w.bbox), "fonts": w.fonts,
                "size": None if w.size is None else round(w.size, 2),
                "bold": w.bold, "italic": w.italic, "text": w.text, "raw_text": w.raw_text,
                "glyphs": [g + 1 for g in w.glyphs], "glyph_ids": w.glyph_ids,
                "joined_from": w.joined_from,
                "region": None if w.region is None else w.region + 1,
            })
    return out


def region_records(doc) -> list[dict]:
    """`regions`: one record per legacy region (D-19), numbered from 1 as the
    placeholders in the text are"""
    return [{"page": page.index + 1, "region": r.index + 1, "line": r.line + 1,
             "bbox": _box(r.bbox), "fonts": r.fonts, "words": [w + 1 for w in r.words],
             "raw_text": r.raw_text}
            for page in doc.pages for r in page.legacy_regions]


def glyph_records(doc) -> list[dict]:
    """UP-CLI-1 `glyphs`: one record per glyph, numbered from 1"""
    out = []
    for page in doc.pages:
        word_of = {gi: w.index for w in page.words for gi in w.glyphs}
        for g in page.glyphs:
            flags = [name for name, on in (("synthetic", g.synthetic),
                                           ("actual_text", g.actual_text),
                                           ("unattributed", g.unattributed),
                                           ("invisible", g.invisible)) if on]
            flags += [f"repeat_{r}" for r in g.repeats]
            word = word_of.get(g.index)
            out.append({
                "page": page.index + 1, "glyph": g.index + 1,
                "word": None if word is None else word + 1,
                "font": g.font, "size": round(g.size, 2), "bbox": _box(g.bbox),
                "origin": [round(v, 2) for v in g.origin],
                "glyph_id": g.actual_text_glyph_ids if g.actual_text else g.glyph_id,
                "render_mode": g.render_mode,
                "line_width": None if g.line_width is None else round(g.line_width, 3),
                "flags": flags, "raw_text": g.text,
            })
    return out


def _tsv(columns: list[str], rows: list[list]) -> str:
    return "\n".join(["\t".join(columns), *("\t".join(cell(v) for v in r) for r in rows)])


def words_tsv(records: list[dict]) -> str:
    cols = ["page", "line", "word", "x0", "y0", "x1", "y1", "font", "size", "bold", "italic",
            "region", "text", "raw_text"]
    return _tsv(cols, [[r["page"], r["line"], r["word"], *(r["bbox"] or [None] * 4),
                        "; ".join(r["fonts"]), r["size"], r["bold"], r["italic"], r["region"],
                        r["text"], r["raw_text"]] for r in records])


def regions_tsv(records: list[dict]) -> str:
    cols = ["page", "region", "line", "x0", "y0", "x1", "y1", "font", "words", "raw_text"]
    return _tsv(cols, [[r["page"], r["region"], r["line"], *(r["bbox"] or [None] * 4),
                        "; ".join(r["fonts"]), len(r["words"]), r["raw_text"]]
                       for r in records])


def glyphs_tsv(records: list[dict]) -> str:
    cols = ["page", "glyph", "word", "font", "size", "x0", "y0", "x1", "y1", "origin_x",
            "origin_y", "glyph_id", "render_mode", "line_width", "flags", "raw_text"]
    return _tsv(cols, [[r["page"], r["glyph"], r["word"], r["font"], r["size"], *r["bbox"],
                        *r["origin"], r["glyph_id"], r["render_mode"], r["line_width"],
                        ",".join(r["flags"]), r["raw_text"]] for r in records])


def json_records(records: list[dict]) -> str:
    """a JSON array, one record per line"""
    if not records:
        return "[]"
    return "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n]"


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


# ---- commands


def cmd_text(args) -> int:
    doc = read(args)
    report(doc)
    write_output(doc.text(), args.output)
    return 0


def cmd_words(args) -> int:
    doc = read(args)
    report(doc)
    records = word_records(doc)
    write_output(json_records(records) if args.format == "json" else words_tsv(records),
                 args.output)
    return 0


def cmd_regions(args) -> int:
    doc = read(args)
    report(doc)
    records = region_records(doc)
    write_output(json_records(records) if args.format == "json" else regions_tsv(records),
                 args.output)
    return 0


def cmd_glyphs(args) -> int:
    doc = read(args)
    report(doc)
    records = glyph_records(doc)
    write_output(json_records(records) if args.format == "json" else glyphs_tsv(records),
                 args.output)
    return 0


def cmd_json(args) -> int:
    doc = read(args)
    report(doc)
    write_output(doc.to_json(indent=args.indent, glyphs=not args.no_glyphs), args.output)
    return 0


def cmd_fonts(args) -> int:
    write_output(fonts_table(read(args)), args.output)
    return 0


def cmd_show(args) -> int:
    from pathlib import Path

    from unipdf import show

    out = args.output or str(Path(args.pdf).with_suffix(".show.html").name)
    doc = read(args)
    report(doc)
    if out.lower().endswith(".png"):
        written = show.write_png(doc, args.pdf, out, zoom=args.zoom or 2.0,
                                 clusters=args.clusters)
    else:
        show.write_html(doc, args.pdf, out, zoom=args.zoom or 1.5, clusters=args.clusters)
        written = [out]
    for path in written:
        print(path, file=sys.stderr)
    return 0


def add_common(p: argparse.ArgumentParser, output_help: str = "output file (default: stdout)"
               ) -> None:
    p.add_argument("pdf")
    p.add_argument("-p", "--pages", help="pages, e.g. '1', '1-5', '1,3,7-10'")
    p.add_argument("-o", "--output", help=output_help)
    p.add_argument("--no-repair", action="store_true", help="do not repair ToUnicode maps")
    p.add_argument("--font", help="use this converter for every font")
    p.add_argument("--font-map", action="append", metavar="FONT=CONVERTER",
                   help="use CONVERTER for FONT (repeatable), e.g. 'Nirmala UI=nirmalaui'")
    p.add_argument("--rawdict-lines", action="store_true",
                   help="one output line per PyMuPDF line, no visual rows (the R layout)")
    p.add_argument("--no-join", action="store_true", help="do not join split words")
    p.add_argument("--j2", type=float, metavar="RATIO",
                   help="also join words across a generated space narrower than RATIO x "
                        "font size (off by default; e.g. 0.15)")
    p.add_argument("--convert-actual-text", action="store_true",
                   help="run converters over /ActualText too, as R does (D-18)")
    p.add_argument("--keep-legacy", action="store_true",
                   help="read legacy 8-bit fonts as R does instead of leaving their words "
                        "out (D-19)")
    p.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                   help="log converter and repair messages")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="unipdf", description="Hindi and Marathi text from PDFs as Unicode",
        epilog="Exit status: 0 on success, also when text is missing (see the warnings on "
               "stderr); 1 when the PDF cannot be read or an option value is wrong.")
    ap.add_argument("-v", "--verbose", action="store_true", help="log converter and repair messages")
    sub = ap.add_subparsers(dest="command", required=True)

    t = sub.add_parser("text", help="the Unicode text of a PDF")
    add_common(t)
    t.set_defaults(fn=cmd_text)

    w = sub.add_parser("words", help="one row per word: page, line, word, box, font, size, "
                                     "bold, italic, legacy region, text, raw text")
    add_common(w)
    w.add_argument("--format", choices=["tsv", "json"], default="tsv",
                   help="tab-separated (default) or a JSON array with glyph ids")
    w.set_defaults(fn=cmd_words)

    r = sub.add_parser("regions", help="one row per region of words in legacy 8-bit fonts, "
                                       "which the text leaves out: page, box, font, words")
    add_common(r)
    r.add_argument("--format", choices=["tsv", "json"], default="tsv",
                   help="tab-separated (default) or a JSON array with word numbers")
    r.set_defaults(fn=cmd_regions)

    g = sub.add_parser("glyphs", help="one row per glyph: box, origin, glyph id, raw text")
    add_common(g)
    g.add_argument("--format", choices=["tsv", "json"], default="tsv",
                   help="tab-separated (default) or a JSON array")
    g.set_defaults(fn=cmd_glyphs)

    j = sub.add_parser("json", help="the whole document model as JSON (specs/JSON_SCHEMA.md)")
    add_common(j)
    j.add_argument("--indent", type=int, help="indent the JSON by this many spaces")
    j.add_argument("--no-glyphs", action="store_true",
                   help="leave out the pages' glyphs and runs (most of the size)")
    j.set_defaults(fn=cmd_json)

    f = sub.add_parser("fonts", help="font table: converter, resolution rule, bold, italic")
    add_common(f)
    f.set_defaults(fn=cmd_fonts)

    s = sub.add_parser("show", help="page images with word boxes, to check geometry")
    add_common(s, output_help="output .html (default: <pdf name>.show.html here) or .png "
                              "(one per page: name-<page>.png)")
    s.add_argument("--clusters", action=argparse.BooleanOptionalAction, default=True,
                   help="draw akshara boxes too (default: yes)")
    s.add_argument("--zoom", type=float, help="image scale (default 1.5 for HTML, 2 for PNG)")
    s.set_defaults(fn=cmd_show)
    return ap


def main(argv: list[str] | None = None) -> int:
    import pymupdf

    from unipdf.pipeline import PasswordRequired

    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.CRITICAL,
                        format="%(name)s: %(levelname)s %(message)s")
    if not os.path.exists(args.pdf):
        print(f"unipdf: no such file: {args.pdf}", file=sys.stderr)
        return 1
    try:
        return args.fn(args)
    except PasswordRequired:
        print(f"unipdf: {args.pdf} is encrypted and needs a password", file=sys.stderr)
        return 1
    except pymupdf.FileDataError as e:
        print(f"unipdf: cannot read {args.pdf} as a PDF: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"unipdf: {e}", file=sys.stderr)
        return 1
