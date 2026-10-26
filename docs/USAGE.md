# Using unipdf in a pipeline

unipdf reads a Hindi or Marathi PDF and gives back its text as Unicode, word
by word, each word with its box on the page, its font, size, bold and italic,
and what the PDF itself said before conversion. This guide is for code that
calls it; the full field list of its JSON is
[`specs/JSON_SCHEMA.md`](../specs/JSON_SCHEMA.md).

- [Install](#install)
- [Quick start](#quick-start)
- [`unipdf.open()`](#unipdfopen)
- [What a document holds](#what-a-document-holds)
- [Coordinates](#coordinates)
- [Which output to use](#which-output-to-use)
- [Recipes](#recipes)
- [Errors](#errors)
- [Logging](#logging)
- [Speed and concurrency](#speed-and-concurrency)
- [A complete example](#a-complete-example)
- [Versions](#versions)

## Install

Pin a release tag:

```toml
# pyproject.toml
dependencies = ["unipdf @ git+https://github.com/mukundesh/unipdf@v0.2.1"]
```

```sh
uv add "unipdf @ git+https://github.com/mukundesh/unipdf@v0.2.1"
# or
pip install "unipdf @ git+https://github.com/mukundesh/unipdf@v0.2.1"
```

Python 3.12 or later. unipdf pins PyMuPDF to exactly 1.28.2: how glyphs and
characters are matched up was measured on that version. If your pipeline
needs another PyMuPDF, run unipdf's tests against it before changing the pin.

## Quick start

```python
import unipdf

doc = unipdf.open("order.pdf")          # a path, or the PDF's bytes

print(doc.text())                       # all pages, separated by "--- Page Break ---"

for page in doc.pages:
    for word in page.words:
        print(page.index, word.text, word.bbox, word.size, word.bold)

for issue in doc.issues:                # what could not be read, and why
    print(issue.severity, issue.code, issue.message)

data = doc.to_dict(glyphs=False)        # JSON-ready dict, without per-glyph detail
```

The same from the command line:

```sh
unipdf text order.pdf                    # text
unipdf words order.pdf                   # one row per word (TSV), or --format json
unipdf json --no-glyphs order.pdf        # the whole model as JSON
unipdf regions order.pdf                 # boxes of the text unipdf could not read
unipdf show -p 1 order.pdf -o page.html  # the page with its word boxes, to check by eye
```

## `unipdf.open()`

`unipdf.open(source, **options) -> Document` reads the whole document (or
the pages asked for) at once. The defaults are what you want for a
pipeline; the options exist for checking and for special cases.

| argument | default | CLI | meaning |
|---|---|---|---|
| `source` | | `PDF` | a path, or the PDF's bytes |
| `pages` | `None` | `-p 1,3-5` | 0-based page numbers (the CLI's are 1-based); `None` = all |
| `repair` | `True` | `--no-repair` | repair broken font maps before reading |
| `force` | `None` | `--font CONV` | one converter for every font |
| `font_map` | `None` | `--font-map FONT=CONV` | a converter for named fonts |
| `join` | `True` | `--no-join` | join words PyMuPDF split before a vowel sign |
| `rawdict_lines` | `False` | `--rawdict-lines` | one output line per PyMuPDF line, no merging into visual rows |
| `j2` | `None` | `--j2 RATIO` | also join across a made-up space narrower than `RATIO` × font size (try 0.15) |
| `actual_text` | `"bypass"` | `--convert-actual-text` | `"convert"` runs converters over a PDF's ActualText too |
| `row_tolerance` | `0.2` | | how far apart, in font sizes, two baselines can be and still be one row |
| `legacy` | `"skip"` | `--keep-legacy` | `"keep"` passes legacy 8-bit fonts through instead of leaving them out |

`--rawdict-lines --no-join --convert-actual-text --keep-legacy` gives the
text of the old `read_pdf.py`, byte for byte. Converter names are
indic2unicode's: `unipdf.converter_names()` lists them.

`unipdf.convert(converter, text)` converts a string that is not in a PDF -
text typed in a legacy font, say: `unipdf.convert("chanakya", "fdlku")`.

## What a document holds

```
Document
├── pages: [Page]
│   ├── index, width, height, rotation
│   ├── lines: [Line]            text of the row, its words (→ page.words)
│   ├── words: [Word]            text, bbox, size, bold, italic, line (→ page.lines),
│   │                            clusters (aksharas with boxes), region, glyphs (→ page.glyphs)
│   ├── legacy_regions: [LegacyRegion]   text unipdf did not read: box, words (→ page.words)
│   ├── glyphs: [Glyph]          every glyph: its PDF text, box, glyph id, font, render mode
│   └── runs: [Run]              conversion units: font, converter, raw and converted text
├── fonts: [Font]                per font name: converter used, bold/italic and why
├── issues: [Issue]              what could not be done
└── source, options, repaired
```

The Python objects and the JSON have the same fields under the same names;
`specs/JSON_SCHEMA.md` lists them all. Everything that points to something
else does so by position in its **page's** list, from 0: `line.words` are
positions in `page.words`, `word.line` a position in `page.lines`,
`word.glyphs` positions in `page.glyphs`.

What most pipelines need:

| you want | use |
|---|---|
| the text | `doc.text()`, `page.text()`, or `line.text` for each `page.lines` |
| words with boxes | `page.words`: `text`, `bbox`, `line` |
| aksharas with boxes | `word.clusters`: `text`, `bbox` |
| font size, bold, italic | `word.size`, `word.bold`, `word.italic` (and `*_evidence` for why) |
| what the PDF said before conversion | `word.raw_text` |
| text unipdf could not read | `page.legacy_regions` |
| whether to trust a page | `doc.issues` with that `page` |

`glyphs`, `runs` and `fonts[].programs` are detail for checking a result,
not for using it.

### Text that is left out

Some fonts are not read, and their text is marked rather than guessed:

- **Legacy 8-bit fonts** (DVB-TTSurekh, DVBW-TTYogesh, MG Shree, Kruti Dev,
  AkrutiDevPriya, …) put Devanagari shapes on Latin letters. Their words
  keep their box and `raw_text` but have `text` `""` and a `region`;
  consecutive ones on a line form a `LegacyRegion`, and `line.text` and
  `doc.text()` hold `⟦8bit:N⟧` where the region was (N = `region.index` +
  1). Read them from the page image (see the recipe below).
- **Pages without a text layer** (scans) give no words and an issue
  `no_text_layer`.

## Coordinates

All boxes are `[x0, y0, x1, y1]` in PDF points (1/72 inch), origin at the
**top left** of the page **as it is displayed**, y growing downwards - the
same space as `page.width` × `page.height` and as the image PyMuPDF renders
of the page. On a rotated page (`page.rotation` 90, 180 or 270) they are
already turned to match.

To scale a box to a page image of `W` × `H` pixels (`page` from
`doc.pages`, `word` from `page.words`):

```python
sx, sy = W / page.width, H / page.height
x0, y0, x1, y1 = word.bbox
pixel_box = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
```

or to fractions of the page: divide x by `page.width` and y by
`page.height`.

A word's box is the union of its glyphs' boxes, and a glyph's box runs from
the font's ascender to its descender rather than hugging the ink: it is a
little taller than the letters, and a vowel sign can stick out sideways by
about a tenth of the font size.

## Which output to use

| output | how | size (a 164 KB, 5-page PDF) |
|---|---|---|
| text | `doc.text()` / `unipdf text` | 22 KB |
| words | `unipdf words` (TSV) | 122 KB |
| JSON without glyphs | `doc.to_dict(glyphs=False)` / `unipdf json --no-glyphs` | 1.6 MB |
| full JSON | `doc.to_dict()` / `unipdf json` | 6.1 MB |

The full JSON is about 40 times the size of the PDF, three quarters of it
per-glyph records. Keep it for checking; store the JSON without glyphs. The
word positions in it still say which glyphs a word came from, if you need
to go back to the full form.

The tables of `unipdf words`, `glyphs` and `regions` number pages, lines,
words and glyphs **from 1**; the JSON and the Python objects number from 0.

## Recipes

### Text of each page

```python
import unipdf

pages = [page.text() for page in unipdf.open(path).pages]
```

### Words with boxes as fractions of the page

```python
import unipdf

rows = []
for page in unipdf.open(path).pages:
    for w in page.words:
        if not w.text or w.bbox is None:      # legacy words have no text
            continue
        x0, y0, x1, y1 = w.bbox
        rows.append({
            "page": page.index, "line": w.line, "text": w.text,
            "box": [x0 / page.width, y0 / page.height,
                    x1 / page.width, y1 / page.height],
            "size": w.size, "bold": w.bold,
        })
```

### Read the text unipdf left out, with OCR

Render the region from the page image, OCR it, and put the result where the
placeholder stands:

```python
import pymupdf, unipdf

doc = unipdf.open(path)
pdf = pymupdf.open(path)
for page in doc.pages:
    if not page.legacy_regions:
        continue
    texts = {}
    for region in page.legacy_regions:
        clip = pymupdf.Rect(region.bbox) + (-2, -2, 2, 2)    # a little margin
        image = pdf[page.index].get_pixmap(clip=clip, dpi=300)
        texts[region.index] = my_ocr(image.tobytes("png"))   # your OCR
    page_text = page.text()
    for index, text in texts.items():
        page_text = page_text.replace(f"⟦8bit:{index + 1}⟧", text)
```

`get_pixmap(clip=...)` takes the same displayed-page coordinates unipdf
gives, rotated pages included.

### Flag pages that need a look

```python
from collections import Counter

import unipdf

doc = unipdf.open(path)
trouble = Counter(i.page for i in doc.issues if i.severity == "warning" and i.page is not None)
left_out = {p.index: len(p.legacy_regions) for p in doc.pages if p.legacy_regions}
scanned = [i.page for i in doc.issues if i.code == "no_text_layer"]
```

Some issues are about the whole document and have `page` `None` -
`legacy_font` gives its pages in `issue.context["pages"]`. The codes:

| code | what it means for you |
|---|---|
| `no_text_layer` | the page is a scan: no text, use OCR |
| `legacy_font` | words in that font are left out, as regions |
| `no_converter` | a font's text looks like a legacy encoding unipdf does not know by name: its text may be gibberish |
| `unconverted_char` | a character was dropped in conversion |
| `converter_error` | a run could not be converted; its raw text stands |
| `repair_failed` | font maps could not be repaired; text may be wrong throughout |
| `joined_words`, `unjoined_glyph`, `provenance_unavailable` | information only |

### Many files

```python
from concurrent.futures import ProcessPoolExecutor

import unipdf


def read_one(path):
    try:
        return path, unipdf.open(path).to_dict(glyphs=False), None
    except Exception as e:                    # see Errors
        return path, None, f"{type(e).__name__}: {e}"


with ProcessPoolExecutor() as pool:
    for path, data, error in pool.map(read_one, paths, chunksize=4):
        ...
```

Use processes, not threads (see below). `tools/compare_docint.py` in this
repository runs this way over 1,551 documents.

## Errors

`unipdf.open()` raises:

| exception | when |
|---|---|
| `FileNotFoundError` | the path does not exist |
| `pymupdf.FileDataError` | the file is not a PDF, or is too damaged to open |
| `unipdf.PasswordRequired` | the PDF is encrypted |
| `ValueError` | an unknown converter in `force` / `font_map`, or a bad option value |

Anything else - a font it cannot repair, a converter that fails on a run,
a page with no text - is not raised: the document is read as far as it can
be and the problem is in `doc.issues`.

The command line exits 0 (also when there are warnings, which it prints on
stderr), 1 when the PDF cannot be read or an option value is wrong, 2 for
usage errors.

## Logging

unipdf never prints; it logs through Python's `logging`:

| logger | what |
|---|---|
| `unipdf` | every issue as it is recorded: warnings at `WARNING`, the rest at `DEBUG` |
| `fix_tounicode` | what the font repair did (`INFO`, `DEBUG`) |
| converter class names (`Sakal`, `MangalGlyphs`, `DVOTSurekh`, …) | characters a converter had no rule for (`WARNING`) |
| `fontTools` | font parsing (`DEBUG`) |

Everything of consequence is also in `doc.issues`, so a pipeline can turn
the logging down and read the issues instead:

```python
import logging
logging.getLogger("unipdf").setLevel(logging.ERROR)
logging.getLogger("fix_tounicode").setLevel(logging.ERROR)
# the converters log under their class names; this quiets everything below ERROR:
logging.disable(logging.WARNING)
```

## Speed and concurrency

About 0.8 seconds of CPU per document over the 1,551 PDFs of the mahagri
collection (1 to 329 pages, 4 at the median); a 15-page order takes about
1 second. Building indic2unicode's converters, once per document, is 0.1 s
of that. The whole document is held in memory while it is read.

PyMuPDF is not safe to use from several threads at once: run documents in
parallel with processes (`ProcessPoolExecutor`, `multiprocessing`), one
document per call. Each call builds its own converters, so calls do not
share state.

## A complete example

`unipdf json --indent 2` of a one-word Google Docs PDF, with four of its
six glyphs and one of its two runs left out:

```json
{
  "schema_version": "0.2",
  "source": {"filename": "hindi.pdf", "sha256": "37e7bf106c13fbdd8d07d4d1905195478c5e7c42523f73f313949bd27dd136d7", "size": 15251},
  "options": {
    "pages": null,
    "repair": true,
    "force": null,
    "font_map": {},
    "join": true,
    "rawdict_lines": false,
    "j2": null,
    "actual_text": "bypass",
    "row_tolerance": 0.2,
    "legacy": "skip"
  },
  "pages": [
    {
      "index": 0,
      "width": 612.0,
      "height": 792.0,
      "rotation": 0,
      "blocks": [0],
      "lines": [
        {
          "index": 0,
          "block": 0,
          "bbox": [72.0, 68.665, 90.64, 87.141],
          "text": "हिंदी ",
          "words": [0],
          "sources": [
            [0, 0]
          ]
        }
      ],
      "words": [
        {
          "index": 0,
          "line": 0,
          "text": "हिंदी",
          "raw_text": "िहंदी",
          "bbox": [72.0, 68.665, 90.64, 87.141],
          "glyphs": [0, 1, 2, 3, 4],
          "glyph_ids": [465, 161, 562, 145, 547],
          "fonts": ["Mangal"],
          "size": 11.0,
          "bbox_level": "word",
          "joined_from": null,
          "join_rules": null,
          "unattributed": [],
          "clusters": [
            {"text": "हिं", "bbox": [72.0, 68.665, 81.463, 87.141], "glyphs": [0, 1, 2]},
            {"text": "दी", "bbox": [81.457, 68.665, 90.64, 87.141], "glyphs": [3, 4]}
          ],
          "sizes": [11.0],
          "font_runs": [
            {"font": "Mangal", "text": "हिंदी", "raw_text": "िहंदी", "bbox": [72.0, 68.665, 90.64, 87.141], "glyphs": [0, 1, 2, 3, 4], "size": 11.0, "bold": false, "bold_evidence": [], "italic": false, "italic_evidence": []}
          ],
          "bold": false,
          "bold_evidence": [],
          "italic": false,
          "italic_evidence": [],
          "region": null
        }
      ],
      "runs": [
        {
          "index": 0,
          "block": 0,
          "line": 0,
          "font": "Mangal",
          "converter": "mangal_glyphs",
          "rule": 1,
          "raw": "िहंदी",
          "text": "हिंदी",
          "glyphs": [0, 1, 2, 3, 4],
          "pieces": [
            ["ह", [1]],
            ["ि", [0]],
            ["ं", [2]],
            ["द", [3]],
            ["ी", [4]]
          ],
          "actual_text": false,
          "provenance": "piece",
          "logical": true,
          "error": null
        }
      ],
      "glyphs": [
        {"index": 0, "text": "ि", "glyph_id": 465, "origin": [72.0, 82.318], "bbox": [72.0, 68.665, 75.443, 87.141], "font": "Mangal", "size": 11.0, "block": 0, "line": 0, "render_mode": 0, "repeats": [], "line_width": null, "color": 0, "opacity": 1.0, "seqno": 1, "synthetic": false, "actual_text": false, "actual_text_glyph_ids": null, "unattributed": false, "actual_text_ignored": true},
        {"index": 1, "text": "ह", "glyph_id": 161, "origin": [75.435, 82.318], "bbox": [75.435, 68.665, 81.463, 87.141], "font": "Mangal", "size": 11.0, "block": 0, "line": 0, "render_mode": 0, "repeats": [], "line_width": null, "color": 0, "opacity": 1.0, "seqno": 1, "synthetic": false, "actual_text": false, "actual_text_glyph_ids": null, "unattributed": false, "actual_text_ignored": true}
      ],
      "legacy_regions": []
    }
  ],
  "fonts": [
    {
      "name": "Mangal",
      "converter": "mangal_glyphs",
      "rule": 1,
      "matched": "Mangal",
      "repaired": true,
      "repaired_as": "Mangal",
      "programs": [
        {
          "xref": 4,
          "pdf_name": "AAAAAA+Mangal",
          "type": "Type0",
          "encoding": "Identity-H",
          "embedded": true,
          "has_tounicode": true,
          "format": "ttf",
          "descriptor": {"ItalicAngle": 0, "Flags": 4},
          "names": {"family": "Mangal", "subfamily": "Regular", "full_name": "Mangal", "version": "Version 5.90a", "postscript_name": "Mangal"},
          "weight": 400,
          "fs_selection": 64,
          "mac_style": 0,
          "italic_angle": 0.0,
          "error": null
        }
      ],
      "bold": false,
      "bold_evidence": [],
      "italic": false,
      "italic_evidence": []
    },
    {
      "name": "ArialMT",
      "converter": null,
      "rule": 4,
      "matched": null,
      "repaired": false,
      "repaired_as": null,
      "programs": [
        {
          "xref": 5,
          "pdf_name": "BAAAAA+ArialMT",
          "type": "Type0",
          "encoding": "Identity-H",
          "embedded": true,
          "has_tounicode": true,
          "format": "ttf",
          "descriptor": {"ItalicAngle": 0, "Flags": 4},
          "names": {"family": "Arial", "subfamily": "Regular", "full_name": "Arial", "version": "Version 5.10a", "postscript_name": "ArialMT"},
          "weight": 400,
          "fs_selection": 64,
          "mac_style": 0,
          "italic_angle": 0.0,
          "error": null
        }
      ],
      "bold": false,
      "bold_evidence": [],
      "italic": false,
      "italic_evidence": []
    }
  ],
  "issues": [],
  "repaired": {"Mangal": "Mangal"}
}
```

Note how the word हिंदी came from glyphs 0-4 drawn in the order ि ह ं द ी:
`raw_text` is that order, `text` the Unicode order, and `runs[0].pieces`
says which glyph each character came from. The ActualText the PDF carries
over ि ह was not used, since the font was repaired, so the glyphs say
`actual_text_ignored`.

A legacy region, the first word in it, the line's text and the issue that
counts it (`unipdf json --no-glyphs` of a page set in DVB-TTYogesh):

```json
{"index": 0, "line": 0, "bbox": [323.999, 46.78, 506.574, 63.439], "fonts": ["DVB-TTYogesh,Bold", "DVB-TTYogesh,Bold+1"], "words": [0, 1, 2], "raw_text": "¯Öã−ÖÔÃÖã¬ÖÖ×¸üŸÖ ¾ÖêŸÖ−ÖÁÖê\"Öß²ÖÖ²ÖŸÖ ¯Öã−ÖÙ¾Ö»ÖÖê#ú−Ö"}
{"index": 0, "line": 0, "text": "", "raw_text": "¯Öã−ÖÔÃÖã¬ÖÖ×¸üŸÖ", "bbox": [323.999, 46.78, 375.616, 63.439], "fonts": ["DVB-TTYogesh,Bold", "DVB-TTYogesh,Bold+1"], "region": 0}
"⟦8bit:1⟧"
{"id": "issue:000001", "severity": "warning", "code": "legacy_font", "message": "DVB-TTYogesh,Bold is a legacy 8-bit font (dv-tt): 23 words left out, in 7 regions", "page": null, "font": "DVB-TTYogesh,Bold", "bbox": null, "context": {"family": "dv-tt", "words": 23, "regions": 7, "pages": [0]}}
```

## Versions

- The package version (`unipdf.__version__`, the git tag) changes with any
  release.
- The JSON says its own `schema_version`; it changes when a field is added,
  removed or changes meaning, and `specs/JSON_SCHEMA.md` ends with what
  changed in each. Check it if you store JSON and read it back later.
- The text for a given PDF can change between releases when a conversion is
  fixed; the reasons are recorded in `specs/REQUIREMENTS.md` (§1,
  decisions).
