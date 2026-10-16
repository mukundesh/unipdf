# unipdf

Hindi and Marathi text from PDFs as correct Unicode, with word boxes and font
attributes. The text conversion is indic2unicode, absorbed unchanged
(`src/unipdf/i2u/`). Geometry comes from PyMuPDF glyphs.

Status: **M2**. `unipdf text` gives indic2unicode's text with visual rows
and split words joined; the library gives words with boxes, raw text and
glyph ids. Font attributes (bold, italic) arrive in M4, the `words` / `json`
commands in M5. See `specs/`.

```sh
uv sync
uv run unipdf text input.pdf
uv run unipdf text -p 1,3-5 input.pdf -o out.txt
uv run unipdf text --font-map DVB-TTSurekh=surekh input.pdf
# R's text byte for byte (the parity oracle's layout)
uv run unipdf text --rawdict-lines --no-join --convert-actual-text input.pdf
uv run pytest                 # about 2 min; -m "not slow" skips the largest
```

```python
import unipdf
doc = unipdf.open("input.pdf")
doc.text()
for w in doc.iter_words():
    print(w.text, w.bbox, w.raw_text, w.glyph_ids, w.size)
```

## Layout

| Path | What |
|---|---|
| `specs/` | REQUIREMENTS (Draft 4), IMPLEMENTATION_PLAN, SPIKES |
| `src/unipdf/i2u/` | indic2unicode at `2cf31cf`, imports rewritten only (see `UPSTREAM`; check with `tools/check_upstream.sh`) |
| `src/unipdf/pipeline.py` | `unipdf.open()`: repair → glyphs → runs → rows → words |
| `src/unipdf/model.py`, `issues.py` | Document / Page / Line / Word / Run / Glyph, issues |
| `src/unipdf/pdf/` | repair; glyph records: `rawdict` joined to `texttrace` (D-15), ActualText (D-18) |
| `src/unipdf/convert/resolve.py` | which converter reads a font (UP-FN-2..5) |
| `src/unipdf/convert/provenance.py`, `runs.py` | tracked conversion (output → glyphs), runs |
| `src/unipdf/layout/` | visual rows, words, J1/J2 joins |
| `src/unipdf/reference.py` | the reference pipeline R, the parity oracle (REQUIREMENTS §7.2) |
| `tests/i2u/` | indic2unicode's testdata/expected (41 converters) |
| `tests/corpus/` | parity corpus: `manifest.yaml`, `pdfs/`, `golden/` (R's output) |
| `tools/` | `build_corpus.py`, `make_golden.py`, `check_upstream.sh` |
| `spikes/m0/` | M0 spike scripts and overlays |

## License

`src/unipdf/i2u/` is GPLv3 (see its `LICENSE`); PyMuPDF is AGPL. unipdf's
own license is not chosen yet.
