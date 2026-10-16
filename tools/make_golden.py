"""Write R's output for every corpus PDF (UP-VF-3):

    tests/corpus/golden/<id>.txt    R's text, as `unipdf text --rawdict-lines --no-join`
    tests/corpus/golden/<id>.json   R's runs: per page, block, line, the font run's
                                    font, converter, rule, raw and converted text

    uv run python tools/make_golden.py [ID ...]
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "tests"))

from corpusdata import corpus_pdfs, golden_paths

from unipdf.reference import read_reference


def main(ids):
    logging.disable(logging.CRITICAL)
    for entry, pdf in corpus_pdfs():
        if ids and entry["id"] not in ids:
            continue
        if pdf is None:
            print(f"{entry['id']}: PDF missing, skipped", file=sys.stderr)
            continue
        doc = read_reference(str(pdf))
        txt, js = golden_paths(entry["id"])
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(doc.text(), encoding="utf-8")
        data = doc.to_dict()
        data["path"] = entry.get("file") or entry["source"]
        js.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{entry['id']}: {len(doc.pages)} pages, {len(doc.text())} chars", file=sys.stderr)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
