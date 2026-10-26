# unipdf — Implementation Plan

Implements [REQUIREMENTS.md](REQUIREMENTS.md) (Draft 3). Requirement IDs
(UP-…, D-…) refer to that document.

## 0. Principles

1. **Parity first, features second.** Every milestone keeps the converter
   regression (41/41 passing today) and, from M2 on, the PDF parity gate green.
   A milestone is not done while either is red.
2. **Absorb mechanically, then change.** Code is copied in and its imports
   rewritten with no other edits; the regression proves the copy. Behavioural
   changes come later, one at a time, each behind a test.
3. **Additive changes to converters.** Provenance (UP-AL) is a second path
   through `BaseFont`; the default `to_unicode` output is never allowed to
   change (UP-AL-3).
4. **Measure before building** where the requirements rest on an assumption
   (M0).

Baseline measured on 2026-10-15 (PyMuPDF 1.28.2, sample `202606122029536001.pdf`):
`FontConv()` 0.11 s; `fix_document` 0.04 s; `rawdict` 5 pages 0.04 s;
`get_texttrace` 5 pages 0.01 s; `regression.py` 41/41 OK. Performance
(UP-NF-3) is not expected to need work; it is checked, not engineered.

## 1. Target layout

```
Try/indic2unicode/unipdf/
  pyproject.toml            uv project; pymupdf==1.28.2 (pinned), ply, fonttools;
                            extra [show]: pillow. Python >= 3.12. Script: unipdf
  specs/                    REQUIREMENTS.md, IMPLEMENTATION_PLAN.md, SPIKES.md
  src/unipdf/
    __init__.py             open(), convert(), convert_with_provenance()
    i2u/                    absorbed indic2unicode (D-5, D-9)
      fontconv.py  fonts/  langs/  fix_tounicode.py
    model.py                Document/Page/Line/Word/Glyph/Font dataclasses, JSON
    issues.py               IssueBag (ported from cidpdf)
    pdf/
      repair.py             fix_document wrapper, repair status per font (UP-RP)
      glyphs.py             rawdict (+ texttrace join) -> Glyph records (UP-EX)
      fonts.py              font records, fontTools metadata, bold/italic (UP-FN-1, UP-AT)
    convert/
      resolve.py            converter resolution (UP-FN-2..5)
      runs.py               run assembly, per-document converter instances (UP-CV)
      provenance.py         tracked conversion, pre-pass adapters (UP-AL)
    layout/
      rows.py               rawdict lines -> visual rows (UP-LY-2)
      words.py              split, J1/J2 joins, word boxes (UP-LY-4..5)
    reference.py            pipeline R (§7.2)
    pipeline.py             open() orchestration
    cli.py                  text | words | glyphs | json | fonts | show
    show.py                 page overlay (UP-CLI-3)
  tests/
    i2u/testdata/ i2u/expected/        copied from indic2unicode
    corpus/manifest.yaml  corpus/pdfs/  corpus/golden/
    hand/words.yaml                    hand-checked boxes (UP-VF-6)
    test_*.py
  tools/
    build_corpus.py         pick corpus PDFs by font coverage
    make_golden.py          run R, write golden text
```

`Try/indic2unicode/` is not a git repository; `unipdf/` gets its own
(`git init` at M1 step 1).

## 2. Milestones

Sizes are relative (S ≈ a day, M ≈ 2–4 days, L ≈ a week) for one person.

### M0 — Spikes (S–M) — **done 2026-10-15, all pass; see SPIKES.md**

Answer the three assumptions the design rests on; write results to
`specs/SPIKES.md`, amend REQUIREMENTS if any fails. Code lives in a scratch
directory, not in `src/`.

| Spike | Question | Method | Pass | If it fails |
|---|---|---|---|---|
| S1 | Can every `rawdict` char be joined to its `texttrace` glyph (for glyph id, render mode, seqno, over-print)? | Join per page on (font, origin ± 0.01 pt), then by order within span. Run on ~20 corpus PDFs. Also record: does texttrace show the over-printed duplicates `rawdict` dropped? Bit meanings of `char_flags`. | ≥ 99.9 % chars joined; misses explained | Take render mode/flags at span level from `rawdict`, glyph id only where joined; UP-EX-1 amended |
| S2 | Does token provenance work without changing output? | In a scratch copy of `BaseFont`, implement the tracked pipeline (§3) for `chanakya`, `sakal`, `arialuni_glyphs`. Compare `to_unicode` vs tracked text over their `testdata` and the corpus runs. | Identical on 100 % of inputs; every output char has ≥ 1 source index | Run-level provenance for the failing converter (UP-AL-2) |
| S3 | Is `rawdict`'s char box good enough for words (D-14)? | Overlay word boxes (union of char boxes) on 5 pages of 3 fonts at 150 dpi; inspect matras, reph, conjuncts. | Boxes cover ink, neighbouring lines' boxes overlap ≤ 20 % | Try texttrace box, then ink box; record in D-14 |

Exit: SPIKES.md written; REQUIREMENTS amended if needed.

Outcome: S1 99.97 % joined (all misses `/ActualText`); S2 0 mismatches over
168k testdata lines and 18k corpus runs; S3 D-14 confirmed. REQUIREMENTS →
Draft 4 (D-15, D-16, UP-EX-7, UP-FN-6, UP-AL-7, OQ-8). Prototypes kept in
`unipdf/spikes/m0/`: `s1_join.py` seeds M2 step 3, `tracked.py` seeds M3
steps 1–2.

### M1 — Skeleton, absorption, reference pipeline, corpus (M) — **done 2026-10-16**

1. `git init`; `uv init --package`; `pyproject.toml` with pinned deps;
   `ruff` config; `pytest`.
2. Copy `indic2unicode/{fontconv.py,fonts,langs,tools/fix_tounicode.py,
   testdata,expected}` as of its current commit (`2cf31cf`); record that
   commit in `src/unipdf/i2u/UPSTREAM`.
3. Rewrite imports only: `indic2unicode.` → `unipdf.i2u.` (36 files),
   `indic2unicode.tools.fix_tounicode` → `unipdf.i2u.fix_tounicode`. No other
   edits. Port `regression.py` to `tests/test_i2u_regression.py`
   (parametrised per font; Devanagari = gate, others = smoke, UP-VF-1).
   Must be 41/41.
4. `convert/resolve.py` (UP-FN-2..5). Unit tests include the two bugs found
   in `read_pdf.py`: unrepaired `Mangal` → no converter; `NudiUni01e`
   unrepaired → no converter (not `nudi`); repaired `Nirmala UI` →
   `nirmalaui_glyphs`; `DVOT-SurekhMR,Bold` → `dvotsurekh` repaired or not.
5. `reference.py` = R exactly as REQUIREMENTS §7.2 (PyMuPDF → repair →
   rawdict → per line same-font span groups → resolve → FontConv →
   `\n` / `\n\n`). Independent of the rest of unipdf on purpose: it is the
   oracle.
6. Corpus (UP-VF-3):
   - `tools/build_corpus.py` scans PDFs under `~/orgpedia` (fonts via
     `get_fonts`, no extraction), maps each font through `resolve`, and picks
     a small set covering every in-scope converter ≥ 2 times, plus 2 scanned,
     2 mixed Hindi/English, 1 multi-numbering Sakal, 1 with signatures,
     1 Word-produced Nirmala UI/Mangal, 1 Google-Docs Mangal. Converters with
     no PDF in `~/orgpedia` are listed as gaps in the manifest.
   - Copy chosen PDFs into `tests/corpus/pdfs/` if the total is < 100 MB,
     else store paths + sha256 in the manifest and skip missing files in CI.
   - `tools/make_golden.py` writes R's text per PDF to `tests/corpus/golden/`.
7. `unipdf text --rawdict-lines --no-join` wired straight to `reference.py`
   for now (UP-VF-4a trivially true; becomes a real check in M2).

Exit: regression 41/41; resolver tests; corpus manifest + goldens committed.

Outcome: 113 tests green (41 converter regressions + 2, 47 resolver, 23
corpus goldens, 4 CLI). `tools/check_upstream.sh` proves `i2u/` = upstream
`2cf31cf` + import rewrite. Found and changed on the way:
- Resolver rule 3 "sound map" exception (REQUIREMENTS UP-FN-2). R therefore
  fixes a third read_pdf.py defect: पश्चिम, not पश्चमि, on the Word export.
  On the 19 spike PDFs R == read_pdf.py byte for byte except that one file.
- OQ-9 (ActualText vs converters) opened; recommendation for M2.
- Corpus: 23 PDFs (21 MB, copied), 4 marked `known_bad` (Google Docs
  ActualText, two DVB-TT legacy fonts per D-17, Lohit-Devanagari which has no
  converter). Gaps: chanakya, aryan2, surekh, abhishek (no PDF among 44,517
  scanned), lossy arialuni/nirmalaui (repair-off only), Sakal two-numbering
  PUA text (none found). These are covered by testdata only.

### M2 — Glyph model, runs, text with rows and joins (L) — **done 2026-10-16**

Outcome: 278 tests green (`uv run pytest`, 2 min 15 s; `-m "not slow"`
skips two line-by-line provenance files). The parity gate (`test_parity.py`)
passes on all 23 corpus PDFs: every run equals R's, words equal R's, the R
layout is R byte for byte. Changes against the steps below, all recorded in
REQUIREMENTS Draft 5 (*[M2]*):

- The glyph join (step 3) runs on a second `rawdict` made with
  `TEXT_IGNORE_ACTUALTEXT`. ActualText is found by diffing the two per line.
  Result: 100 % joined, against 99.97 % in S1 (whose misses were all
  ActualText).
- OQ-9 was decided (b) = D-18: ActualText bypasses the converter. It fixes
  `Hindi-Google.pdf`. `--convert-actual-text` gives R's behaviour.
- The tracked path (M3 step 1) and its equivalence test (M3 step 3, testdata
  part) moved here: step 4's `unconverted_char` needs it, and with it word
  glyphs come from provenance directly. The raw-split boxes of step 6 were
  never built.
- J1 is limited to logical-order text (`Run.logical`): on the
  Lohit-Devanagari PDF (unconverted, visual order) it joined `भोपाल,` +
  `िदनांक`.
- Step 9: J2 is off by default. The corpus's 83 synthetic spaces are all real
  word gaps (gap / size ≥ 0.151); no `रे लवे`-type document. `--j2 RATIO`
  enables it.
- Step 8: with visual rows, words are compared as a multiset per page: one
  OCR-layer page lists a row's lines right to left.
- UP-RP-4 is per document (`fix_document` is one call; D-16).
- UP-NF-3: `unipdf text` over the corpus 5.5 s against R's 4.0 s (×1.38).

1. `model.py`: dataclasses from REQUIREMENTS §5.9 (top-left points,
   `(x0, y0, x1, y1)`), `to_dict`/`to_json` with `schema_version`, stable
   ordering (UP-MD-2). `issues.py`: port cidpdf `Issue`/`IssueBag`.
2. `pdf/repair.py`: wraps `ToUnicodeFixer`; per-font repaired/`repaired_as`;
   `repair_failed` issue (UP-RP-1..4).
3. `pdf/glyphs.py`: Glyph records from `rawdict` (text, bbox, synthetic,
   font, size) joined to texttrace by D-15 (port `spikes/m0/s1_join.py`):
   glyph id, `texttrace` origin, render mode, seqno, repeated-pass types and
   line width. `gid = -1` continuations merge into their glyph (UP-EX-4);
   ActualText spans are joined as groups (UP-EX-7); `unjoined_glyph` issue.
   Test: join rate ≥ 99.9 % per corpus PDF excluding ActualText spans.
4. `convert/runs.py`: per rawdict line, maximal same-font glyph runs; one
   converter instance per font per document, created lazily, runs fed in
   page/line order (UP-CV-1..2); `converter_error`, `unconverted_char`
   issues (UP-CV-4..5). `unconverted_char` comes from the tracked path
   (input indices with no output, UP-AL-7), not from a hook in
   `BaseFont.report_error`, so the absorbed code stays unedited (D-16).
5. `layout/rows.py` (UP-LY-2): merge same-block lines with baseline
   difference ≤ 0.2 × size, sort by x, join with one space.
6. `layout/words.py` (UP-LY-4..5): split on whitespace; J1; J2 using the
   synthetic flag and gap of the glyphs either side of the space.
   Word boxes at this stage = union of the run's glyphs per word, found by
   splitting the *raw* run at the same spaces — valid only where the converter
   does not move characters across a space (true for every word of the
   corpus if the M2 check passes; replaced by provenance in M3).
7. `pipeline.py` + `unipdf.open()`, `Document.text()`; `unipdf text` with
   `--no-join`, `--rawdict-lines`, `-p`, `-o`.
8. Parity gate `tests/test_parity.py` (UP-VF-4): per corpus page, run-level
   equality with R, then word-sequence equality modulo recorded joins.
   UP-VF-4a: `--rawdict-lines --no-join` byte-identical to golden.
9. J2 calibration: dump every synthetic space with its gap (ratio to size)
   and the words either side; pick the threshold; if the corpus has no
   `रे लवे`-type document, disable J2 by default and record why (UP-LY-6).

Exit: parity gate green on the whole corpus; `unipdf text` usable.

### M3 — Provenance and geometry (L) — **done 2026-10-16**

Outcome: abhishek adapter (every in-scope converter now has piece-level
provenance); akshara clusters on every word; `unipdf show` (HTML with hover
details, or PNG); `test_geometry.py`: UP-VF-5 invariants on all 24 PDFs and
45 hand-checked words (UP-VF-6). Overlays reviewed for Sakal, DVOT-Surekh,
Nirmala UI (Word export, ActualText), Mangal (Google Docs), Arial Unicode
MS. HTML instead of pillow: the browser shapes Devanagari labels; PNG via
PyMuPDF's own drawing, so `pillow` is not needed.

*After M2: steps 1 and 3 and the word half of step 4 are done (M2 outcome).*

1. ~~Tracked path (UP-AL-1) in `convert/provenance.py`~~ — done in M2.
2. Pre-pass adapters (UP-AL-2) in `convert/provenance.py`: `chanakya`
   (ZWJ/ZWNJ deletion map), `sakal` (identity), `arialuni_glyphs` and
   subclasses (per-segment offsets) are done in M2. Remaining: `abhishek`
   (its own token pipeline, tracked version of `drop_shared_tokens`; run-level
   until then, issue `provenance_unavailable`).
3. ~~Equivalence test (UP-AL-3, UP-VF-2)~~ — done in M2
   (`test_provenance_equivalence.py`; corpus runs through `test_parity.py`).
4. Cluster boxes where available (UP-AL-5). Word boxes from provenance
   (UP-AL-4, UP-AL-6) are done in M2.
5. `show.py` + `unipdf show` (port cidpdf `visualize_pdf` drawing, word and
   cluster boxes, text labels).
6. Geometry invariants test (UP-VF-5) over the corpus; hand-checked
   `tests/hand/words.yaml` (~50 words: reph, matra-i, conjuncts, nukta,
   each in-scope font) checked with tolerance 0.5 pt (UP-VF-6).

Exit: UP-VF-2, -5, -6 green; overlays reviewed for 3 fonts.

### M4 — Font records and attributes (M) — **done 2026-10-16**

Outcome: `pdf/fonts.py` (programs per font name, read before repair,
fontTools names/OS2/head/post, descriptor), `attributes.py` (glyph, font
run, word), `unipdf fonts`. UP-VF-7: 30 hand-labelled words. Corpus gained
`c024` (Times New Roman,Italic beside Sakal), the only italic case. Rules
recorded in REQUIREMENTS UP-AT-2/3 *[M4]*. 397 tests green.

1. `pdf/fonts.py`: font record (UP-FN-1) — PDF name/type/encoding/embedded/
   ToUnicode from `get_fonts(full=True)` and the font dict; font program via
   `doc.extract_font(xref)`; names/OS2/head via fontTools (port cidpdf
   `_font_names_from_file`, `_populate_font_version_metadata`).
2. Bold evidence (UP-AT-2): port cidpdf `_annotate_font_bold` (name keywords,
   descriptor weight, OS/2 weight, fsSelection) + render mode 1/2 + over-print
   (from S1) + `char_flags` fake-bold. Italic (UP-AT-3). Per run and per word
   (UP-AT-4); size majority (UP-AT-1).
3. Hand-labelled attribute set (UP-VF-7): bold font, stroked bold, over-print
   bold, italic, plain.

Exit: UP-VF-7 green; `unipdf fonts` shows converter + resolution rule.

### M5 — CLI, JSON, docs, retirement (S–M) — **done 2026-10-16**

Outcome: `unipdf words` / `glyphs` (TSV or JSON) / `json`; `-o`, `-v` on
every command; stderr summary with the new `no_converter` warning
(REQUIREMENTS UP-CLI-2 *[M5]*); exit codes 0/1/2. `specs/JSON_SCHEMA.md`,
pinned to the output by `tests/test_json.py`. UP-API-2 string API
(`unipdf.convert`, `convert_with_provenance`, `converter_names`). README
rewritten. `../read_pdf.py` and `../read_pdf_cidpdf.py` replaced by notes;
their last versions are in `tools/retired/`. Finding: `--font-map
DVB-TTYogesh=yogesh` converts most of c011 but not the glyphs Word put in the
`DVB-TTYogesh+1` font object, which is the input-adapter work of D-17/OQ-8.

**After M5 — legacy fonts left out (D-19, 2026-10-26).** No input adapter:
legacy 8-bit fonts are recognised by family name (`convert/legacy.py`) and
not read. Their words become legacy regions (`Page.legacy_regions`, a
`⟦8bit:N⟧` placeholder in the text, `unipdf regions`, `legacy_font` issue);
the `--font-map` hint is gone. The parity gate and the reference pipeline
run with `legacy="keep"`; `tests/test_legacy.py` checks that only legacy
fonts change. `tools/legacy_font_docs.py` lists the mahfin2 documents with a
legacy font from `pdfinfos/`.

**After M5 — the mahagri2024 comparison (D-20, D-21, 2026-10-27).**
`tools/compare_docint.py` matches unipdf's words by box against another
pipeline's `doc.json` for 1,551 documents. What it showed wrong in unipdf
was fixed: ActualText that Word writes wrong is no longer used (D-20), and
indic2unicode's Sakal Marathi, Mangal, Nirmala UI and Kokila handling was
changed upstream (D-21). Words where only unipdf's spelling is impossible
went from 2,141 to 141, U+FFFD from 608 to 0; the golden text was rebuilt
(`tools/make_golden.py`) and changed only where it was wrong.


1. `unipdf words` (TSV/JSON), `glyphs`, `json`, `fonts` (UP-CLI-1);
   stderr summary of missing conversions (UP-CLI-2); exit codes.
2. JSON schema doc (`specs/JSON_SCHEMA.md`) with `raw_text` and glyph ids
   in default output (D-13).
3. README: install with `uv`, usage, how conversion and geometry relate, known
   limitations (extractor word splits, D-14 box choice).
4. Replace `read_pdf.py` / `read_pdf_cidpdf.py` with a note pointing to
   `unipdf`.

Exit: all tests green; README; a fresh `uv sync && uv run unipdf words
202606122029536001.pdf` works.

## 3. Design note: tracked conversion in `BaseFont`

The passes compare tokens by value (`t in self.jumpover`,
`compose == tokens[i:i+n]`, `self.num_before(t)`) so tokens cannot simply
become objects. The tracked path runs the same passes over **pairs**
`(token, sources)` with every comparison made on `pair[0]`:

- `tokenize_tracked`: from each ply token, `sources = range(lexpos,
  lexpos + len(value))`; `multiple_tokens` expansion gives each produced
  token the same `sources`.
- `compose_tokens_tracked`: replacement pairs get the union of the replaced
  pairs' sources (a list replacement gives the union to each element).
- `jump_before_tokens_tracked` / `jump_after_tokens_tracked`: identical logic,
  moving pairs.
- `tokens_to_unicode_tracked`: returns `[(text, sources), …]`; a token that
  maps to `None` (dropped) contributes its sources to nothing and is reported.

**Decided by S2 (SPIKES §2.1):** separate functions in
`convert/provenance.py`, applied to unmodified converter instances. No edit
to `i2u/`. They gave 0 mismatches over all Devanagari testdata and the corpus
at ×1.04–1.13 cost. The equivalence test pins them to `to_unicode`. The
refactor option below is not taken. Original text kept for the record:

To keep a single source of truth, the existing pass bodies are refactored to
take a `key` function (`key=lambda t: t` default, `key=lambda p: p[0]`
tracked) **only if** the regression stays 41/41 after the refactor; otherwise
the tracked versions are separate methods and an equivalence test pins them
together. S2 decides which.

Pre-pass adapters return `(new_string, index_map)` where `index_map[i]` is
the set of original indices for new index `i`; provenance is composed through
it.

## 4. Test inventory

| Test | Requirement | From milestone |
|---|---|---|
| `test_i2u_regression.py` | UP-VF-1 | M1 |
| `test_resolve.py` | UP-FN-2..5 | M1 |
| `test_parity.py` | UP-VF-4, -4a, UP-CV-3 | M2 |
| `test_rows_words.py` (synthetic fixtures) | UP-LY-2..5 | M2 |
| `test_provenance_equivalence.py` | UP-AL-3, UP-VF-2 | M3 (S2 prototype in M0) |
| `test_geometry.py` | UP-VF-5, -6 | M3 |
| `test_attributes.py` | UP-AT, UP-VF-7 | M4 |
| `test_cli.py` | UP-CLI-* | M5 |
| `test_json.py` | UP-MD-1, -2 (JSON_SCHEMA.md) | M5 |
| `test_strings.py` | UP-API-2 | M5 |
| `test_legacy.py` | D-19 | after M5 |
| `test_actual_text.py` | D-20 | after M5 |

## 5. Order and parallelism

M0 → M1 → M2 → {M3, M4} → M5. M3 and M4 are independent once M2's model
exists. Within M1, corpus building (step 6) can run alongside steps 2–5.

## 6. Decision points

- After **M0**: if S1 fails, per-glyph render mode/over-print evidence
  degrades to span level (affects UP-AT-2 only). If S2 fails for a converter,
  that converter gets run-level boxes. If S3 fails, D-14 changes.
- After **M2 step 9**: J2 on or off by default. *Decided: off (M2 outcome).*
- ~~After **M3**: whether to keep M2's raw-split word boxes as a fast mode.~~
  Not built: M2 takes word glyphs from provenance.
