"""Build the parity corpus (UP-VF-3, IMPLEMENTATION_PLAN M1 step 6).

    uv run python tools/build_corpus.py scan ROOT... --cache scan.jsonl
    uv run python tools/build_corpus.py pick --cache scan.jsonl

scan  lists the fonts of the first pages of every PDF under the roots (no
      text extraction, no repair) and appends one JSON line per PDF to the
      cache. Rerunning skips PDFs already in the cache.
pick  classifies the fonts with the converter they would get, picks a small
      set covering every in-scope converter at least twice plus the special
      cases, confirms each pick by running R on it, and writes
      tests/corpus/manifest.yaml (and copies the PDFs if they fit).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf
import yaml

from unipdf.convert.resolve import (
    RULE_NAME,
    RULE_READS_UNREPAIRED,
    ConverterResolver,
    strip_subset,
)
from unipdf.i2u.fix_tounicode import get_font_converter, get_glyph_fixes
from unipdf.i2u.fontconv import FontConv

HERE = Path(__file__).resolve().parent.parent
CORPUS = HERE / "tests" / "corpus"
MAX_COPY_BYTES = 100 * 1024 * 1024
SCAN_PAGES = 2

# converters of Hindi and Marathi (D-6) a PDF can reach
IN_SCOPE = [
    "sakal", "dvotsurekh", "mangal_glyphs", "arialuni_glyphs", "nirmalaui_glyphs",
    "chanakya", "aryan2", "surekh", "yogesh", "abhishek", "arialuni", "nirmalaui",
]
PER_CONVERTER = 2
# FontConv's converters for the broken maps of unrepaired PDFs (resolve.py rule 3)
LOSSY = {"arialuni", "nirmalaui"}

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "site-packages"}


# ---------------------------------------------------------------- scan

def iter_pdfs(roots):
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
            for f in files:
                if f.lower().endswith(".pdf"):
                    yield os.path.join(d, f)


def scan_one(path):
    rec = {"path": path}
    try:
        rec["size"] = os.path.getsize(path)
        doc = pymupdf.open(path)
        rec["pages"] = doc.page_count
        rec["producer"] = (doc.metadata or {}).get("producer", "")
        rec["creator"] = (doc.metadata or {}).get("creator", "")
        rec["signed"] = doc.get_sigflags() > 0
        fonts, images = set(), 0
        for pno in range(min(SCAN_PAGES, doc.page_count)):
            page = doc[pno]
            fonts.update(f[3] for f in page.get_fonts())
            images += len(page.get_images())
        rec["fonts"] = sorted(fonts)
        rec["images"] = images
        doc.close()
    except Exception as e:  # noqa: BLE001 - a broken PDF is a scan result
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def cmd_scan(args):
    done = set()
    if os.path.exists(args.cache):
        with open(args.cache) as f:
            done = {json.loads(line)["path"] for line in f}
    n, t0 = 0, time.time()
    with open(args.cache, "a") as out:
        for path in iter_pdfs(args.roots):
            if path in done:
                continue
            out.write(json.dumps(scan_one(path), ensure_ascii=False) + "\n")
            n += 1
            if n % 1000 == 0:
                out.flush()
                print(f"{n} scanned, {time.time() - t0:.0f}s", file=sys.stderr)
    print(f"{n} scanned, {len(done)} were cached", file=sys.stderr)


# ---------------------------------------------------------------- pick

def likely_converters(fonts, resolver):
    """the converters a PDF's fonts would get. Repair status is unknown at
    scan time, so a font the repair knows is counted as both its repaired
    pass and, for the record, 'repairable'"""
    out = set()
    for font in fonts:
        name = strip_subset(font)
        if get_glyph_fixes(name) is not None:
            conv = get_font_converter(name)
            if conv:
                out.add(conv)
        res = resolver.resolve(font, None)
        if res.rule in (RULE_READS_UNREPAIRED, RULE_NAME) and res.converter:
            out.add(FontConv_name(res.converter))
    return out


_FC = None


def FontConv_name(name):
    """FontConv keys several names onto one converter object; report the
    canonical lowercase name"""
    global _FC
    if _FC is None:
        _FC = FontConv()
        _FC.canon = {}
        for key, obj in _FC.converters.items():
            _FC.canon.setdefault(id(obj), []).append(key)
    keys = _FC.canon[id(_FC.converters[name])]
    lower = [k for k in keys if k.islower()]
    return min(lower or keys)


def run_reference(path):
    from unipdf.reference import read_reference

    doc = read_reference(path)
    convs = Counter()
    for page in doc.pages:
        for block in page.blocks:
            for line in block:
                for run in line.runs:
                    if run.converter:
                        convs[FontConv_name(run.converter)] += len(run.raw)
    text = doc.text()
    deva = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return doc, convs, deva, latin


def sakal_numberings(path):
    """which of Sakal's two private-use numberings the Sakal runs of a PDF
    show marks of (fonts/marathi/sakal.py pick_numbering)"""
    from unipdf.i2u.fonts.marathi.sakal import Sakal
    from unipdf.reference import font_runs

    sakal, seen = Sakal(), set()
    try:
        doc = pymupdf.open(path)
    except Exception:  # noqa: BLE001 - unreadable PDFs are not candidates
        return seen
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for font, raw in font_runs(line):
                    if "sakal" not in font.lower():
                        continue
                    counts = [len([c for c in raw if c in marks]) for marks in sakal.numbering_marks]
                    if counts[0] != counts[1]:
                        seen.add(0 if counts[0] > counts[1] else 1)
        if len(seen) == 2:
            break
    return seen


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_pick(args):
    logging.disable(logging.CRITICAL)
    resolver = ConverterResolver(FontConv().converters, legacy="keep")  # R's converters
    recs = []
    with open(args.cache) as f:
        for line in f:
            rec = json.loads(line)
            if "error" not in rec and rec.get("pages") and rec["size"] < args.max_pdf_mb * 2**20:
                recs.append(rec)
    random.seed(args.seed)
    random.shuffle(recs)

    by_conv = defaultdict(list)
    for rec in recs:
        for conv in likely_converters(rec["fonts"], resolver):
            by_conv[conv].append(rec)

    picks = {}  # path -> manifest entry

    def confirm(rec, want_conv=None):
        try:
            doc, convs, deva, latin = run_reference(rec["path"])
        except Exception as e:  # noqa: BLE001 - a broken PDF is a scan result
            print(f"  R failed on {rec['path']}: {e}", file=sys.stderr)
            return None
        if want_conv and want_conv not in convs:
            return None
        return {"convs": dict(convs), "deva": deva, "latin": latin, "doc": doc}

    def add(rec, why, info):
        entry = picks.setdefault(rec["path"], {
            "path": rec["path"], "pages": rec["pages"], "size": rec["size"],
            "producer": rec["producer"], "fonts": rec["fonts"],
            "converters": sorted(info["convs"]), "reasons": []})
        entry["reasons"].append(why)

    # every in-scope converter, PER_CONVERTER times, confirmed by R
    gaps = {}
    for conv in IN_SCOPE:
        if conv in LOSSY:
            gaps[conv] = "only reached with repair off (rule 3); R always repairs"
            continue
        have = sum(1 for e in picks.values() if conv in e["converters"])
        tried = 0
        for rec in by_conv.get(conv, []):
            if have >= PER_CONVERTER or tried >= 40:
                break
            if rec["path"] in picks:
                continue
            tried += 1
            info = confirm(rec, conv)
            if info:
                add(rec, f"converter:{conv}", info)
                have += 1
        print(f"{conv:18s} candidates={len(by_conv.get(conv, [])):5d} picked={have}", file=sys.stderr)
        if have < PER_CONVERTER:
            gaps[conv] = f"{have} PDF(s) found under the scanned roots"

    # special cases
    def first(pred, why, n=1, need_text=True):
        got = 0
        for rec in recs:
            if got >= n:
                break
            if rec["path"] in picks and why in picks[rec["path"]]["reasons"]:
                continue
            if not pred(rec):
                continue
            info = confirm(rec)
            if info is None or (need_text and info["deva"] < 50):
                continue
            if why == "mixed_hindi_english" and info["latin"] < 0.2 * info["deva"]:
                continue
            add(rec, why, info)
            got += 1
        if got < n:
            gaps[why] = f"{got} of {n} found"

    deva_fonts = lambda rec: bool(likely_converters(rec["fonts"], resolver))
    first(lambda r: not r["fonts"] and r["images"] > 0, "scanned", 2, need_text=False)
    first(lambda r: deva_fonts(r) and any(k in " ".join(r["fonts"]) for k in ("Times", "Arial,", "Calibri", "Arial\"")),
          "mixed_hindi_english", 2)
    first(lambda r: r["signed"] and deva_fonts(r), "signed", 1)
    first(lambda r: "Microsoft" in (r["producer"] + r["creator"]) and
          any(k in " ".join(r["fonts"]) for k in ("Nirmala", "Mangal")), "word_export", 1)
    # Google Docs Mangal comes from corpus_includes.yaml: the only such PDF
    # has five characters, below what first() asks of a pick
    # reading every page is slow: look at a bounded number of Sakal PDFs
    budget = [60]

    def both_numberings(r):
        if budget[0] <= 0 or r["pages"] < 2 or "sakal" not in likely_converters(r["fonts"], resolver):
            return False
        budget[0] -= 1
        return sakal_numberings(r["path"]) == {0, 1}

    first(both_numberings, "sakal_both_numberings", 1)
    if "sakal_both_numberings" in gaps:
        gaps["sakal_both_numberings"] = (
            "none of 60 Sakal PDFs carries private-use codes (nor 400 sampled in M1); "
            "the two numberings are covered by tests/i2u/testdata/sakal only")

    # the named cases, whatever the picks above
    with open(HERE / "tools" / "corpus_includes.yaml", encoding="utf-8") as f:
        includes = yaml.safe_load(f)
    for inc in includes:
        src = os.path.expanduser(inc["source"])
        rec = next((r for r in recs if r["path"] == src), None) or scan_one(src)
        info = confirm(rec)
        if info is None:
            gaps[inc["source"]] = "named include could not be read"
            continue
        add(rec, inc["reason"], info)
        if inc.get("known_bad"):
            picks[rec["path"]]["known_bad"] = inc["known_bad"]

    entries = sorted(picks.values(), key=lambda e: e["path"])
    total = sum(e["size"] for e in entries)
    copy = total <= MAX_COPY_BYTES
    (CORPUS / "pdfs").mkdir(parents=True, exist_ok=True)
    for i, e in enumerate(entries, 1):
        e["id"] = f"c{i:03d}"
        e["sha256"] = sha256(e["path"])
        if copy:
            dst = CORPUS / "pdfs" / f"{e['id']}.pdf"
            shutil.copyfile(e["path"], dst)
            e["file"] = f"pdfs/{e['id']}.pdf"
        # written with ~ for the home directory, which corpusdata expands
        e["source"] = e.pop("path").replace(os.path.expanduser("~") + os.sep, "~/", 1)
    manifest = {
        "about": "UP-VF-3 parity corpus; built by tools/build_corpus.py pick",
        "copied": copy,
        "total_bytes": total,
        "gaps": gaps,
        "pdfs": entries,
    }
    with open(CORPUS / "manifest.yaml", "w") as f:
        yaml.safe_dump(manifest, f, allow_unicode=True, sort_keys=False, width=100)
    print(f"{len(entries)} PDFs, {total / 2**20:.1f} MB, copied={copy}; gaps: {gaps}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("roots", nargs="+")
    s.add_argument("--cache", required=True)
    s.set_defaults(fn=cmd_scan)
    p = sub.add_parser("pick")
    p.add_argument("--cache", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--max-pdf-mb", type=float, default=8)
    p.set_defaults(fn=cmd_pick)
    args = ap.parse_args()
    pymupdf.TOOLS.mupdf_display_errors(False)
    args.fn(args)


if __name__ == "__main__":
    main()
