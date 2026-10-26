"""Compare unipdf's pages and words with another pipeline's `*.pdf.doc.json`.

The other pipeline (pdf_cid_info, pdf_cid_reader, word_recognizer, …) gives,
per page, words with `text_` and a box as fractions of the page size
(`shape_.top` = top left, `shape_.bot` = bottom right). For each document:

- page counts;
- per page, words are matched one to one by box: the same row (vertical
  overlap at least half the lower word's height) and horizontal IoU at least
  0.5, best pairs first. The other pipeline's boxes are tighter at the top,
  so only the horizontal IoU is scored;
- a matched pair has the same text or not (both NFC); a word left unmatched
  on either side is usually a word split or joined differently;
- order-free: the share of words both give (multiset, F1).

Writes, to the output directory:

    docs.tsv      one row per document
    diffs.tsv     matched words whose text differs: doc page theirs ours fonts
    summary.txt   totals, and the most frequent text differences

    uv run python tools/compare_docint.py mahagri2024/input mahagri2024/output -o OUT
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

IOU = 0.5


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def theirs_words(page: dict) -> list[tuple[str, tuple[float, float, float, float]]]:
    w, h = page["width_"], page["height_"]
    out = []
    for word in page.get("words") or []:
        s = word["shape_"]
        out.append((nfc(word["text_"]), (s["top"]["x"] * w, s["top"]["y"] * h,
                                         s["bot"]["x"] * w, s["bot"]["y"] * h)))
    return out


def _pair_score(a, b) -> float:
    """horizontal IoU of two boxes on the same row, else 0"""
    vov = min(a[3], b[3]) - max(a[1], b[1])
    if vov < 0.5 * min(a[3] - a[1], b[3] - b[1]):
        return 0.0
    inter = min(a[2], b[2]) - max(a[0], b[0])
    if inter <= 0:
        return 0.0
    return inter / (max(a[2], b[2]) - min(a[0], b[0]))


def match(theirs, ours) -> list[tuple[int, int]]:
    """one-to-one pairs (i theirs, j ours), best horizontal IoU first"""
    cands = []
    for i, (_, a) in enumerate(theirs):
        for j, (_, b, _) in enumerate(ours):
            if b is None:
                continue
            s = _pair_score(a, b)
            if s >= IOU:
                cands.append((s, i, j))
    used_i, used_j, pairs = set(), set(), []
    for _, i, j in sorted(cands, reverse=True):
        if i not in used_i and j not in used_j:
            used_i.add(i)
            used_j.add(j)
            pairs.append((i, j))
    return pairs


def bag_f1(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    common = sum((Counter(a) & Counter(b)).values())
    return 2 * common / (len(a) + len(b))


def compare(args: tuple[str, str]) -> dict:
    pdf, doc_json = args
    logging.disable(logging.CRITICAL)
    import unipdf

    row = {"doc": Path(pdf).stem}
    try:
        gold = json.loads(Path(doc_json).read_text(encoding="utf-8"))
        doc = unipdf.open(pdf)
    except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
        row["error"] = f"{type(e).__name__}: {e}"[:200]
        return row
    row.update(pages_theirs=len(gold["pages"]), pages_ours=len(doc.pages))
    totals = Counter()
    diffs = []
    for gpage, page in zip(gold["pages"], doc.pages, strict=False):
        theirs = theirs_words(gpage)
        ours = [(nfc(w.text), w.bbox, w) for w in page.words]
        pairs = match(theirs, ours)
        totals["words_theirs"] += len(theirs)
        totals["words_ours"] += len(ours)
        totals["legacy_ours"] += sum(w.region is not None for _, _, w in ours)
        totals["matched"] += len(pairs)
        for i, j in pairs:
            t, (o, _, w) = theirs[i][0], ours[j]
            if t == o:
                totals["same"] += 1
            elif w.region is not None:
                totals["diff_legacy"] += 1
            else:
                totals["diff"] += 1
                diffs.append((page.index + 1, t, o, "; ".join(w.fonts)))
        totals["bag_common"] += sum((Counter(t for t, _ in theirs)
                                     & Counter(o for o, _, w in ours if w.region is None)).values())
    row.update(totals)
    row["diffs"] = diffs
    return row


COLS = ["doc", "pages_theirs", "pages_ours", "words_theirs", "words_ours", "legacy_ours",
        "matched", "same", "diff", "diff_legacy", "bag_common", "error"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", type=Path, help="directory of PDFs")
    ap.add_argument("output", type=Path, help="directory of *.pdf.doc.json")
    ap.add_argument("-o", "--out", type=Path, required=True, help="directory for the report")
    ap.add_argument("-j", "--jobs", type=int, default=8)
    ap.add_argument("-n", "--limit", type=int, help="only the first N documents")
    args = ap.parse_args(argv)

    jobs = []
    for dj in sorted(args.output.glob("*.pdf.doc.json")):
        pdf = args.input / dj.name.removesuffix(".doc.json")
        if pdf.exists():
            jobs.append((str(pdf), str(dj)))
    jobs = jobs[: args.limit] if args.limit else jobs
    args.out.mkdir(parents=True, exist_ok=True)

    rows = []
    with ProcessPoolExecutor(args.jobs) as ex:
        for k, row in enumerate(ex.map(compare, jobs, chunksize=4), 1):
            rows.append(row)
            if k % 100 == 0:
                print(f"{k}/{len(jobs)}", file=sys.stderr)

    with (args.out / "docs.tsv").open("w", encoding="utf-8") as f:
        print("\t".join(COLS), file=f)
        for r in rows:
            print("\t".join(str(r.get(c, "")) for c in COLS), file=f)
    pairs = Counter()
    with (args.out / "diffs.tsv").open("w", encoding="utf-8") as f:
        print("doc\tpage\ttheirs\tours\tfonts", file=f)
        for r in rows:
            for page, t, o, fonts in r.get("diffs", []):
                print(f"{r['doc']}\t{page}\t{t}\t{o}\t{fonts}", file=f)
                pairs[(t, o)] += 1

    ok = [r for r in rows if "error" not in r]
    tot = Counter()
    for r in ok:
        tot.update({k: v for k, v in r.items() if isinstance(v, int)})
    page_diff = [r for r in ok if r["pages_theirs"] != r["pages_ours"]]
    lines = [
        f"documents: {len(rows)} ({len(rows) - len(ok)} failed in unipdf)",
        f"page count differs: {len(page_diff)}",
        (f"words: theirs {tot['words_theirs']}, ours {tot['words_ours']} "
        f"(of which {tot['legacy_ours']} in legacy regions)"),
        f"matched by box: {tot['matched']} ({100 * tot['matched'] / max(1, tot['words_theirs']):.1f}% of theirs)",
        f"  same text: {tot['same']} ({100 * tot['same'] / max(1, tot['matched']):.2f}% of matched)",
        f"  different text: {tot['diff']}, in legacy regions: {tot['diff_legacy']}",
        (f"order-free shared words: {tot['bag_common']} "
        f"(F1 {2 * tot['bag_common'] / max(1, tot['words_theirs'] + tot['words_ours'] - tot['legacy_ours']):.3f})"),
        "",
        "most frequent differences (count, theirs -> ours):",
        *(f"{n}\t{t}\t{o}" for (t, o), n in pairs.most_common(60)),
    ]
    (args.out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
