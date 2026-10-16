# unipdf

Hindi and Marathi text from PDFs as correct Unicode, with word boxes and font
attributes. The text conversion is indic2unicode, absorbed unchanged
(`src/unipdf/i2u/`). Geometry comes from PyMuPDF glyphs.

Status: **M1**. `unipdf text` runs the reference pipeline: indic2unicode as
`read_pdf.py` uses it, with its converter-choice bugs fixed. Words, boxes and
attributes arrive in M2–M4. See `specs/`.

```sh
uv sync
uv run unipdf text input.pdf
uv run unipdf text -p 1,3-5 input.pdf -o out.txt
uv run unipdf text --font-map DVB-TTSurekh=surekh input.pdf
uv run pytest
```

## Layout

| Path | What |
|---|---|
| `specs/` | REQUIREMENTS (Draft 4), IMPLEMENTATION_PLAN, SPIKES |
| `src/unipdf/i2u/` | indic2unicode at `2cf31cf`, imports rewritten only (see `UPSTREAM`; check with `tools/check_upstream.sh`) |
| `src/unipdf/convert/resolve.py` | which converter reads a font (UP-FN-2..5) |
| `src/unipdf/reference.py` | the reference pipeline R, the parity oracle (REQUIREMENTS §7.2) |
| `tests/i2u/` | indic2unicode's testdata/expected (41 converters) |
| `tests/corpus/` | parity corpus: `manifest.yaml`, `pdfs/`, `golden/` (R's output) |
| `tools/` | `build_corpus.py`, `make_golden.py`, `check_upstream.sh` |
| `spikes/m0/` | M0 spike scripts and overlays |

## License

`src/unipdf/i2u/` is GPLv3 (see its `LICENSE`); PyMuPDF is AGPL. unipdf's
own license is not chosen yet.
