# unipdf

Hindi and Marathi text from PDFs as correct Unicode, with word boxes and font
attributes. The text conversion is
[indic2unicode](https://github.com/mukundesh/indic2unicode), absorbed with
its imports rewritten only (`src/unipdf/i2u/`). Geometry comes from PyMuPDF
glyphs.

Status: **v0.2.2**. **Using it from code: [`docs/USAGE.md`](docs/USAGE.md)** -
the API, the output, coordinates, recipes, errors, logging, a full JSON
example. Every JSON field: [`specs/JSON_SCHEMA.md`](specs/JSON_SCHEMA.md).
Requirements and plan in `specs/`.

## Install

```sh
git clone git@github.com:mukundesh/unipdf.git
cd unipdf
uv sync
uv run unipdf --help
```

As a dependency of another project, pinned to a release tag:

```toml
dependencies = ["unipdf @ git+https://github.com/mukundesh/unipdf@v0.2.2"]
```

PyMuPDF is pinned to 1.28.2, the version the glyph join and boxes were
measured on (`specs/SPIKES.md`); a project that needs another version should
run the tests against it before moving the pin.

To change the absorbed indic2unicode, clone it beside unipdf, as
`tools/check_upstream.sh` and `tools/sync_upstream.sh` expect:

```sh
git clone git@github.com:mukundesh/indic2unicode.git   # next to unipdf/
```

Python 3.12+. Dependencies: PyMuPDF, fontTools, ply.

## Command line

```sh
uv run unipdf text input.pdf                      # Unicode text, pages split by --- Page Break ---
uv run unipdf text -p 1,3-5 input.pdf -o out.txt
uv run unipdf words input.pdf                     # TSV: page line word x0 y0 x1 y1 font size bold italic region text raw_text
uv run unipdf words --format json input.pdf       # the same, plus glyph numbers and glyph ids
uv run unipdf regions input.pdf                   # TSV: words in legacy 8-bit fonts, left out of the text
uv run unipdf glyphs input.pdf                    # TSV: one row per glyph, its box, origin, glyph id, raw text
uv run unipdf json --indent 1 input.pdf           # the whole model (specs/JSON_SCHEMA.md)
uv run unipdf json --no-glyphs input.pdf          # the same without per-glyph records, a quarter the size
uv run unipdf fonts input.pdf                     # converter, resolution rule, PDF font objects, bold/italic evidence
uv run unipdf show -p 1 input.pdf -o page.html    # page image with word and akshara boxes (or page.png)
```

Options common to all commands:

| option | |
|---|---|
| `-p 1,3-5` | pages (1-based) |
| `-o FILE` | output file (default stdout) |
| `--font CONV` | one converter for every font |
| `--font-map FONT=CONV` | a converter for one font (repeatable) |
| `--no-repair` | do not repair ToUnicode maps |
| `--no-join` | keep words the extraction split |
| `--j2 RATIO` | also join across generated spaces narrower than RATIO × size (off) |
| `--rawdict-lines` | one output line per PyMuPDF line, no visual rows |
| `--convert-actual-text` | run converters over `/ActualText` too |
| `--keep-legacy` | read legacy 8-bit fonts as the old script did instead of leaving them out |
| `-v` | log what the repair and converters say |

`--rawdict-lines --no-join --convert-actual-text --keep-legacy` gives the text
of the old `read_pdf.py` (with its two converter-resolution bugs fixed) byte for byte.

The `words` and `glyphs` tables number pages, lines, words and glyphs from 1.
A word's `glyphs` (JSON) are numbers in the `glyphs` table of the same page.
Boxes are PDF points, top-left origin of the page as displayed. In TSV, tab, newline, backslash and
control characters in text are escaped (`\t`, `\n`, `\\`, `\x01`).

Text that is missing or left unconverted is summarised on stderr, e.g.

```
unipdf: warning: DVB-TTYogesh is a legacy 8-bit font (dv-tt): 584 words left out, in 69 regions (legacy_font)
```

## Legacy 8-bit fonts

Fonts like DVB-TTSurekh, DVBW-TTYogesh, MG Shree, Kruti Dev or AkrutiDevPriya
put Devanagari glyphs on the bytes of a Latin code page, and Word's PDF
export loses some of their characters. unipdf does not read them (D-19). It
recognises them by font name (`src/unipdf/convert/legacy.py`) and leaves
their words out, so that another tool, OCR for instance, can read them from
the page image:

- consecutive such words on a line form a **legacy region**, and the text
  holds `⟦8bit:N⟧` in its place (N numbers the regions of a page from 1);
- `unipdf regions` lists them, one row each: page, region, line, box, font,
  number of words, raw text;
- in `unipdf words` their `text` is empty and `region` is N; in JSON a
  word's `region` and `page.legacy_regions` (numbered from 0) say the same.

```
$ unipdf text -p 1 c011.pdf
⟦8bit:1⟧
...
$ unipdf regions -p 1 c011.pdf
page  region  line  x0   y0     x1      y1     font                                   words  raw_text
1     1       1     324  46.78  506.57  63.44  DVB-TTYogesh,Bold; DVB-TTYogesh,Bold+1  3      ¯Öã−ÖÔÃÖã¬ÖÖ×¸üŸÖ ...
```

A legacy font under a name no pattern knows (Word sometimes renames fonts
`MSTT31…`) is read as plain text; if its characters look like an 8-bit
encoding the stderr summary says so (`no_converter`). `--font-map` still
forces a converter on a legacy font.

`tools/legacy_font_docs.py pdfinfos` lists the documents of the mahfin2
collection that use a legacy font, with their word counts.

Exit status is 0 also when there are warnings, 1 when the PDF cannot be read
(missing, not a PDF, encrypted) or an option value is wrong, 2 for usage
errors.

## Python

The short version; [`docs/USAGE.md`](docs/USAGE.md) has the rest.

```python
import unipdf

doc = unipdf.open("input.pdf", pages=[0, 1])
doc.text()
for w in doc.iter_words():
    print(w.text, w.bbox, w.raw_text, w.glyph_ids, w.size, w.bold, w.bold_evidence)
    for c in w.clusters or []:          # aksharas
        print("  ", c.text, c.bbox)
for page in doc.pages:
    for r in page.legacy_regions:       # words in legacy 8-bit fonts, not read
        print(page.index, r.index, r.bbox, r.fonts, r.raw_text)
for issue in doc.issues:
    print(issue.code, issue.message)
doc.to_json()

unipdf.convert("chanakya", "fdlku")                  # indic2unicode's string API
unipdf.convert_with_provenance("chanakya", "fdlku")  # [("क", [1]), ("ि", [0]), ...]
```

`unipdf.open` also takes the PDF as `bytes`. It raises
`unipdf.PasswordRequired` for an encrypted PDF and `pymupdf.FileDataError`
for a file that is not a PDF.

## How conversion and geometry fit together

1. **Repair.** indic2unicode's `fix_tounicode` repairs broken ToUnicode maps
   in memory.
2. **Glyphs.** Each glyph is one record that joins two PyMuPDF sources:
   `rawdict` gives its text and box, and `texttrace` gives its glyph id,
   origin and render mode. `/ActualText` replacements become one record
   standing for the glyphs they replace, except where the ActualText is
   known to be wrong - it holds U+FFFD, or its font was repaired - and its
   glyphs are read instead (D-20; Word writes both).
3. **Runs.** Consecutive glyphs of one font on a `rawdict` line form a run. A
   run's text goes through the converter that `convert/resolve.py` picks for
   the font. One converter instance serves the whole document, as in
   indic2unicode.
4. **Provenance.** The conversion is run in a tracked form, the same passes
   over (token, source indices) pairs, so every piece of output names the
   glyphs it came from. Reordering (`ि`, reph) is handled this way. A test
   pins the tracked text to `to_unicode`.
5. **Layout.** `rawdict` lines on one baseline are merged into visual rows.
   Words are split at spaces. A word the extraction split is joined again
   when its second part starts with a mark (J1).
6. **Words.** A word's box is the union of the glyphs its text came from. Its
   aksharas get boxes the same way. Bold and italic come from the font
   programs (names, OS/2, descriptor) and from how glyphs are drawn: Word's
   fake bold is fill then stroke.

The text is indic2unicode's (D-7). The only differences are words joined
across a split, and ActualText left unconverted.

## Known limitations

- **Boxes are font boxes.** A box runs from the font's ascender to its
  descender (`rawdict`'s box, D-14), not the tight ink outline. A matra can
  spill sideways by up to ~0.12 em, and a line at the very top of a page can
  start a few points above it.
- **Extractor word splits.** Joins happen only where the second part starts
  with a mark (J1). A split between two consonants is left as the extraction
  made it, unless `--j2` is given. J1 is not applied to unconverted text,
  which may be in visual order.
- **Legacy 8-bit fonts are not read** (above). They are found by name only:
  a renamed one is passed through as Latin text, and one that uses only
  ASCII codes looks like English and gets no warning.
- **Fake italic.** Word's fake italic (a slanted text matrix) is not
  detected. Only italic fonts are.
- **Run-level boxes.** A converter with no index map would give one box per
  run, and `clusters` would be null. Every Hindi/Marathi converter in use has
  one.
- **Speed.** unipdf takes about 1.5× the time of the old `read_pdf.py`. Half
  of that is building indic2unicode's converters once per document.

## Tests

```sh
uv run pytest                 # about 2.5 min; -m "not slow" skips the largest
tools/check_upstream.sh       # i2u/ is indic2unicode with imports rewritten only
tools/check_upstream.sh --worktree   # ... against its uncommitted changes
tools/sync_upstream.sh        # copy indic2unicode in again (working tree, or a commit)
```

The parity corpus (`tests/corpus/`, 24 PDFs) holds the reference text,
`golden/`, from the reference pipeline (`src/unipdf/reference.py`). Every
run's text must equal it. Word boxes and attributes are checked against
hand-labelled words in `tests/hand/`.

## Layout

| Path | What |
|---|---|
| `docs/` | `USAGE.md`, the guide for code that calls unipdf |
| `specs/` | REQUIREMENTS, IMPLEMENTATION_PLAN, SPIKES, JSON_SCHEMA |
| `src/unipdf/i2u/` | indic2unicode at `ff7232f` (D-21, D-22), imports rewritten only (see `UPSTREAM`) |
| `src/unipdf/pipeline.py` | `unipdf.open()`: repair → glyphs → runs → rows → words |
| `src/unipdf/model.py`, `issues.py` | Document / Page / Line / Word / Run / Glyph / Font, issues |
| `src/unipdf/pdf/` | repair; glyph records (D-15, D-18); font records |
| `src/unipdf/convert/` | converter resolution, tracked conversion, runs, string API |
| `src/unipdf/layout/` | visual rows, words, joins, aksharas |
| `src/unipdf/attributes.py` | bold/italic evidence |
| `src/unipdf/cli.py`, `show.py` | command line, page overlays |
| `src/unipdf/reference.py` | the reference pipeline, the parity oracle |
| `tests/` | tests; `i2u/` indic2unicode's testdata, `corpus/` parity corpus, `hand/` hand labels |
| `tools/` | corpus and golden builders, `check_upstream.sh` / `sync_upstream.sh`, `legacy_font_docs.py`, `compare_docint.py` (words against another pipeline's `doc.json`), `derive_glyph_table.py` (a glyph table for fix_tounicode from fonts that keep their GSUB), `retired/` old scripts |
| `spikes/m0/` | M0 spike scripts |

## License

`src/unipdf/i2u/` is GPLv3 (see its `LICENSE`); PyMuPDF is AGPL. unipdf's
own license is not chosen yet.
