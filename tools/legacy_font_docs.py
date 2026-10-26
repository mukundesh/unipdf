"""List the documents that use a legacy 8-bit Devanagari font.

Reads the pdfinfos/*.jsonl records (one per PDF: its fonts, with a name, a
type and a word count each) and writes one line per document that has at
least one font of a legacy family, space separated:

    year record_key page_count total_words legacy_words legacy_fonts

`total_words` is the document's word count, `legacy_words` the words set in
legacy fonts, `legacy_fonts` their names (subset prefix removed, spaces
turned into `_`), separated by `|` (names can hold commas), most words
first.

A legacy font is recognised by its name only, with unipdf's family patterns
(src/unipdf/convert/legacy.py): the records carry no glyph data, and an 8-bit
font's text is Latin to the extractor, like English. So a legacy font under a
name no pattern knows (Word's `MSTT31…`, `TTE…t00`, `T1`) is not found.

    uv run python tools/legacy_font_docs.py pdfinfos -o legacy_docs.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from unipdf.convert.legacy import legacy_family

SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")


def scan(paths: list[Path], out, stats: Counter) -> None:
    print("year record_key page_count total_words legacy_words legacy_fonts", file=out)
    for path in paths:
        year = path.stem
        with path.open(encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                stats["documents"] += 1
                words: Counter = Counter()
                for font in (doc.get("fonts") or {}).values():
                    name = SUBSET_PREFIX_RE.sub("", font.get("name") or "")
                    family = legacy_family(name)
                    if family:
                        words[name.replace(" ", "_")] += font.get("word_count", 0)
                        stats[f"family {family}"] += 1
                if not words:
                    continue
                stats["legacy documents"] += 1
                total = (doc.get("language") or {}).get("total_words", 0)
                fonts = "|".join(n for n, _ in words.most_common())
                print(year, doc["record_key"], doc.get("page_count", 0), total,
                      sum(words.values()), fonts, file=out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pdfinfos", type=Path, help="directory of *.jsonl files")
    ap.add_argument("-o", "--output", type=Path, help="output file (default stdout)")
    args = ap.parse_args(argv)
    paths = sorted(args.pdfinfos.glob("*.jsonl"))
    if not paths:
        ap.error(f"no .jsonl files in {args.pdfinfos}")
    stats: Counter = Counter()
    if args.output:
        with args.output.open("w", encoding="utf-8") as out:
            scan(paths, out, stats)
    else:
        scan(paths, sys.stdout, stats)
    for key, n in sorted(stats.items()):
        print(f"{key}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
