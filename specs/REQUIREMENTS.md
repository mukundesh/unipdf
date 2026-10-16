# unipdf — Requirements

Status: **Draft 4** (2026-10-16) — M0 spikes done (SPIKES.md), amendments marked *[M0]*; OQ-8 decided (D-17).

unipdf reads Hindi and Marathi text out of PDFs as correct Unicode **and** says
where every word sits on the page and how it is set (size, bold, italic). It is
built by absorbing two existing libraries in this repository:

| Library | What unipdf takes from it | What unipdf leaves behind |
|---|---|---|
| `indic2unicode/` | All text conversion: `fontconv.py`, `fonts/`, `langs/`, `tools/fix_tounicode.py`. Its output is the definition of correct text. | `tools/pdf_ocr.py` (out of scope) |
| `cidpdf/` | Glyph-level geometry, the document model (glyph → word → line → page), font metadata and bold/italic evidence, the issue model, the CLI filter pattern. | YAML CMaps and everything that reads them, glyph SHA candidates, the ASCII→Devanagari digit remap, docling backend and sidecar, the CMap developer workflow |

---

## 1. Decisions already made

| # | Decision | Source |
|---|---|---|
| D-1 | Text conversion comes from indic2unicode. **No per-font YAML (or any other hand-authored per-font data file) is part of unipdf.** Font knowledge stays in Python converter modules and the tables of `fix_tounicode.py`. | Owner |
| D-2 | Bounding boxes and font characteristics come from the cidpdf approach (glyph-level extraction). | Owner |
| D-3 | unipdf has no connection to docling. | Owner |
| D-4 | AGPL (PyMuPDF/MuPDF) is acceptable for now. | Owner |
| D-5 | indic2unicode and cidpdf are **absorbed** into unipdf (copied in, owned by unipdf), not used as external dependencies. | Owner |
| D-6 | Scope is Hindi and Marathi (Devanagari). | Owner |
| D-7 | indic2unicode's output is the reference. unipdf's text must be identical to it; unipdf does not "improve" conversions in v1. | Owner |
| D-8 | The PDF engine is **PyMuPDF (MuPDF) only**. The patched pypdfium2 is not used. cidpdf's model, layout and attribute logic are ported onto PyMuPDF glyphs. Rationale and evidence: §2. | Owner, Draft 1 §2 |
| D-9 | The converters and `fix_tounicode.py` tables of **all scripts are shipped unchanged**, but only Devanagari is supported and tested (D-6). | Owner |
| D-10 | unipdf lives in this repository, in `Try/indic2unicode/unipdf/`, beside `indic2unicode/` and `cidpdf/`. | Owner |
| D-11 | Layout is built from PyMuPDF's grouping (`rawdict`), not cidpdf's line builders, which are not carried over. `rawdict` lines are the conversion units; output lines are `rawdict` lines merged into visual rows (§5.7). | Owner; row merge added after measurement (§5.7) |
| D-12 | unipdf **joins words** that the extraction split, by the rules of §5.7 (UP-LY-5). This is the one deliberate departure from D-7: it changes whitespace only, every join is recorded, and the parity gate accounts for it (§7.2). | Owner |
| D-13 | Default JSON output includes each word's pre-conversion `raw_text` and the glyph ids behind it. | Owner |
| D-14 | Glyph and word boxes are `rawdict`'s character box (font ascender to descender). *[M0]* Confirmed by S3: ink never extends above or below it; horizontal spill ≤ ~0.12 em on 4 % of words; 3 of 1,297 stacked pairs overlap > 20 %. An ink-tight outline box is a later option, not v1 (needs UP-FN-6's span → xref mapping). | Owner: "try with one and see"; SPIKES §3 |
| D-15 | *[M0]* `rawdict` characters are joined to `texttrace` entries by **sequence first, origin second** (SPIKES §1.2): 99.97 % joined on the spike corpus, every miss inside `/ActualText`. `/ActualText` is honoured as R does. | SPIKES §1 |
| D-16 | *[M0]* The absorbed indic2unicode code is **not edited** beyond the import rewrite. Provenance runs BaseFont's passes as separate functions over (token, sources) pairs on unmodified converter instances, pinned to `to_unicode` by test. | SPIKES §2.1 |
| D-17 | Legacy 8-bit fonts with no resolvable name (`DVB-TTSurekh`, `DVB-TTSurekhEN`, `DVB-TTYogesh`) stay unconverted in v1, matching R; `--font-map` is available. Later, a separate **input adapter** per legacy font maps PyMuPDF's characters to the bytes the converter expects (OQ-8). | Owner, 2026-10-16 |

## 2. The PDF engine (D-8): rationale and evidence

The two libraries sit on different PDF engines: indic2unicode is calibrated on
**PyMuPDF** (MuPDF) extraction; cidpdf uses a **patched pypdfium2** build that
exposes per-glyph CID, glyph id and bbox. Because of D-7 this choice is not
cosmetic. PyMuPDF was chosen (D-8); this section records why.

### 2.1 Why it matters: the converters' input contract

indic2unicode's converters do not take "the text of the PDF". They take **the
exact string PyMuPDF extracts**, including PyMuPDF's quirks, and several of them
depend on those quirks:

- `fonts/marathi/dvotsurekh.py` reads glyphs the ToUnicode map does not name as
  *their glyph id written as a character* — PyMuPDF's fallback
  (`जिल्हाधिकारी` arrives as `'िजÊहािधकारी'`, U+00CA = glyph 202 = half la).
- `fonts/marathi/sakal.py` reads the private-use characters this producer's
  map hands unnamed glyphs, and infers which of two glyph numberings a line is
  in from which PUA codes appear on it.
- The README's Tunga notes: PyMuPDF falls back on the CID; pdftotext drops the
  glyph, and the text is lost for good.
- `*_glyphs` converters (Arial Unicode MS, Nirmala UI, Mangal) expect the glyph
  order of the PDF **after** `fix_tounicode.py` repaired its map in a PyMuPDF
  document.

### 2.2 Evidence: pdfium's per-glyph text is not PyMuPDF's

Measured on PDFs in `~/orgpedia` (same file, per-page non-space character
sequence; "repaired" = after `ToUnicodeFixer.fix_document`, saved and reopened):

| PDF | Fonts | Pages equal (raw / repaired) | Nature of difference |
|---|---|---|---|
| `Try/indic2unicode/202606122029536001.pdf` | Sakal Marathi, DVOT-SurekhMR, TNR | 2/5 · 2/5 | pdfium omits the digital-signature text block; one glyph `-` in MuPDF is `\x02` in pdfium |
| `CID_Glyphs/202604021304472019.pdf` | Sakal Marathi | 3/5 · 3/5 | signature block omitted |
| `pdfium-work/test-pypdfium2/201303141104586205.pdf` | Sakal Marathi, Mangal | 0/7 · 0/7 | pdfium keeps over-printed (fake-bold) duplicate glyphs: `णयय` vs `णय` |
| `Try/playa/Hindi-Google.pdf` | Mangal | 0/1 · 0/1 | different glyph order: `हिदंी` vs `हिंदी`; 2 items with `char_code=0xFFFFFFFF`, `glyph_id=65535` |
| `Try/playa/Hindi-WordDesktop.pdf`, `Hindi-Word365Cloud.pdf` | Nirmala UI | 1/1 · 1/1 | equal — but a glyph mapped to `िं` comes back as **two items with the same CID and bbox**, which cidpdf's overstrike de-duplication would collapse, losing `ं` |
| `order_hi_archive_045.pdf`, `order_mr_current_007.pdf`, `1_Upload_1990.pdf` | (no text layer) | equal | scanned |

Each difference above changes what a converter sees, and therefore its output.

### 2.3 Evidence: PyMuPDF already exposes glyph-level data

PyMuPDF 1.28 gives, without patches:

- `page.get_texttrace()` — per glyph, in content-stream order: Unicode, **glyph
  id**, origin, bbox; per span: font name, size, flags, colour, opacity,
  render type (fill / stroke / invisible), line width, `seqno`.
- `page.get_text("rawdict")` — per character: text, origin, bbox, `synthetic`
  (generated space); per span: font, size, flags, `char_flags` (incl. fake
  bold, stroked, clipped), and the block/line grouping indic2unicode is
  calibrated on.

What it does not give directly is the raw PDF character code (CID) of each
glyph; for Identity-H fonts (all the broken fonts in scope) CID = glyph id.
Neither box is ink-tight: on the sample, texttrace's box spans the font size
(height 12.0 for 12 pt) and `rawdict`'s the font's ascender–descender (height
19.0). The exact bit meanings of `char_flags` and whether texttrace reports the
over-printed duplicates that `rawdict` drops are to be confirmed in M0.

### 2.4 Options considered

| Option | Text parity with indic2unicode (D-7) | Geometry & attributes | Cost / risk |
|---|---|---|---|
| **A. PyMuPDF only** (chosen) | By construction: same engine, same repair, same strings | texttrace + rawdict cover cidpdf's needs; cidpdf's layout and bold/italic logic is ported onto them | Port cidpdf's model/layout off pdfium. No patched binaries to build or ship. |
| B. Patched pdfium only | Needs a "MuPDF-equivalence layer" re-creating MuPDF's fallbacks, de-duplication, ordering and multi-codepoint handling — open-ended, every difference in §2.2 is a parity bug | Native (cidpdf as is) | Highest risk to D-7; custom wheels per platform (`pyproject.toml` pins 4 GitHub-release wheels) |
| C. Both: PyMuPDF for text, pdfium for geometry, joined per glyph | By construction | Native | Two engines must agree on glyph identity and order — they demonstrably do not (§2.2), so the join itself is a new source of errors |

**Chosen: Option A.** It satisfies D-7 by construction and keeps D-2's
substance — glyph-level geometry and attributes, cidpdf's model and logic —
while dropping the patched binary.

---

## 3. Goals and non-goals

### Goals

- G-1 Text of Hindi/Marathi PDFs, identical to indic2unicode's (D-7).
- G-2 A bounding box for every word, line and page region the text comes from,
  and for every output character cluster where that is meaningful (§5.6).
- G-3 Per-word font characteristics: font, size, bold (with evidence), italic.
- G-4 One library, one install, one CLI; no hand-authored per-font data files.
- G-5 Diagnostics that say what could not be converted and where.

### Non-goals (v1)

- Scripts other than Devanagari: their converters ship (D-9) and remain
  reachable through UP-FN-2, but they are not supported, tested or covered by
  the parity gate.
- OCR of scanned PDFs; table/column/reading-order analysis beyond
  lines and blocks; docling integration; PDF writing other than in-memory
  repair.
- Improving indic2unicode's conversions (e.g. resolving Sakal's numbering
  from the glyph's real font instead of guessing per line). Such improvements
  are welcome later as opt-in, never as a silent change of default output.

---

## 4. Glossary

| Term | Meaning |
|---|---|
| Glyph | One drawn shape on the page: glyph id, font, origin, bbox, render mode. |
| Glyph text | The string the extractor assigns a glyph (from ToUnicode, or the extractor's fallback). May be empty or several code points. |
| Repair | `fix_tounicode.ToUnicodeFixer.fix_document`: rewrites broken ToUnicode maps in memory. |
| Font run | Consecutive glyphs on one line in one font, in extraction order — the unit a converter is called on. |
| Converter | An indic2unicode `BaseFont` subclass reached through `FontConv`. |
| Visual order | Glyph drawing order (matra-i before its consonant, reph after its syllable). |
| Logical order | Unicode storage order. Converters map visual → logical. |
| Provenance | For each piece of output text, the set of source glyphs it came from. |
| Reference pipeline (R) | The current indic2unicode path, defined in §7.2. Its output is "correct". |

---

## 5. Functional requirements

Requirement IDs are stable; tests reference them.

### 5.1 Input

- **UP-IN-1** Accept a path or bytes. Encrypted PDFs that open without a
  password are processed; others raise a typed error.
- **UP-IN-2** Accept a page selection (0-based indices in the API, 1-based
  ranges like `1,3-5` in the CLI). Invalid ranges are an error, not a silent
  empty result.
- **UP-IN-3** A PDF with no text layer returns pages with no words and an
  issue `no_text_layer` per page; it is not an error.

### 5.2 Repair

- **UP-RP-1** Run `ToUnicodeFixer.fix_document` on the in-memory document
  before extraction, by default. The input file is never modified.
- **UP-RP-2** Record, per font, whether it was repaired and under which name
  (`fixed_fonts`, `fixed_font_names`), and expose this on the font model.
- **UP-RP-3** Repair can be disabled (`repair=False`); output then equals R
  run without repair.
- **UP-RP-4** If repair raises, log an issue `repair_failed` with the font and
  continue unrepaired for that font, rather than failing the document.

### 5.3 Glyph extraction

- **UP-EX-1** Produce one glyph record per glyph PyMuPDF reports, carrying:
  page, glyph text (exactly as `rawdict` gives it after repair), glyph id,
  origin, bbox (D-14), font reference, font size,
  render mode, colour, opacity, `synthetic`, `char_flags`, `seqno`.
  *[M0]* Built by the D-15 join. Origin comes from `texttrace` (the true pen
  position: `rawdict` moves zero-advance marks to the end of the previous
  glyph). Text and box come from `rawdict`. Glyph id, render mode, `seqno`,
  line width and the repeated-pass record come from `texttrace`. A character
  that does not join keeps its `rawdict` data, with glyph id `null` and an
  issue `unjoined_glyph`.
- **UP-EX-2** The glyph text fed to converters must be byte-identical to the
  `rawdict` text the reference pipeline uses. Any additional source
  (texttrace) is joined to it, never substituted for it.
- **UP-EX-3** Over-printed duplicate glyphs (fake bold) must not appear twice
  in the text. The fact that they existed is kept as bold evidence (UP-AT-2).
  Observed: MuPDF's text has them once where pdfium has them twice
  (`णय` vs `णयय`). *[M0]* `texttrace` repeats the whole span (fill `type 0`,
  then stroke `type 1`, identical glyphs) and `rawdict` keeps one copy. The
  join drops the repeat and records its render type and line width on the
  glyph (9,380 glyphs in 13 of 19 spike PDFs).
- **UP-EX-4** A glyph whose text is several code points (e.g. a repaired
  conjunct `क्ष`, or `िं`) is **one** glyph record with a multi-character
  text; it is never split into several records or de-duplicated.
  *[M0]* `rawdict` gives each code point as its own character (the extra ones
  zero-width at the glyph's end); `texttrace` marks the extra ones `gid = -1`.
  The record is the glyph's character plus the joined `gid = -1` characters
  after it.
- **UP-EX-5** Generated (synthetic) spaces are kept as text — the converters
  were calibrated with them — and flagged so that geometry ignores them.
- **UP-EX-6** Invisible text (render mode 3, e.g. an OCR layer under a scan)
  is extracted and flagged; whether it is included in output is an option,
  default included (matches R).
- **UP-EX-7** *[M0]* `/ActualText`: inside an ActualText span, `rawdict`
  reports the replacement text, not the glyphs' text, as R does. unipdf keeps
  it. Those characters get the glyph ids of the span's glyphs as a group,
  without a 1:1 glyph, and are flagged `actual_text`. (2 of 19 spike PDFs:
  Word and Google Docs exports.)

### 5.4 Font identification and converter resolution

- **UP-FN-1** Each PDF font gets a font record: PDF name, base name (subset
  prefix stripped), xref, type, encoding, embedded yes/no, has-ToUnicode,
  repaired yes/no, and font-program metadata read with fontTools (name table,
  OS/2 weight and fsSelection, head dates, italic angle) — the content of
  cidpdf's `font-info`.
- **UP-FN-2** Converter resolution is a single, deterministic, documented
  function from (font record, repair status) to a converter name or none:
  1. If the font was **repaired** in this document, use
     `fix_tounicode.get_font_converter(repaired name)`.
  2. Else, if the font is one whose converter reads both repaired and
     unrepaired text (`dvotsurekh`, `sakal` per `FONT_CONVERTERS`), use it.
  3. Else, look the font up among `FontConv.converters` keys by exact name,
     subset-stripped name, then `fix_tounicode.font_lookup_key` normalisation.
     *[M1]* Except a font the repair knows how to fix (`get_glyph_fixes`) in a
     document where repair ran and left it unchanged. Its map is sound, so its
     text is already right. FontConv's bare `Nirmala UI` / `Arial Unicode MS`
     keys name lossy converters meant "for a pdf that nothing has repaired".
     Applied to sound text they turn पश्चिम into प्चकम (Word export,
     `order_en_current_021.pdf`). Such a font gets none (rule 4,
     `matched = "sound map"`). With `repair=False` rule 3 applies as written.
  4. Else none: the glyph text is passed through unchanged.
- **UP-FN-3** Resolution must never select a `*_glyphs` reordering converter
  for a font that was not repaired in this document (`fontconv.py` warns this
  turns निर्माण into नर्मिाण), and must not use prefix matching (it maps
  `NudiUni01e` onto the 8-bit `nudi` converter).
- **UP-FN-4** The caller can force a converter for all fonts or per font name
  (`--font chanakya`, `--font-map "DV-TTSurekh=surekh"`). A forced converter is
  applied per font run, never to text of other fonts.
- **UP-FN-5** Every resolution decision is recorded on the font record
  (`converter`, `resolution_rule` = 1–4 or `forced`) and is visible in JSON
  output and `font-info`.
- **UP-FN-6** *[M0]* PyMuPDF's spans name their font but do not give its
  xref, and one page can carry several fonts of one name (sample PDF: three
  `Sakal Marathi`, one Type0 and two TrueType). Font records are therefore
  keyed by base name. A record lists every xref of that name, and metadata
  that differs between them is reported, not guessed. Converters need only the
  name, as in R, so text is unaffected.

### 5.5 Run assembly and conversion

- **UP-CV-1** Converters are invoked per **font run**: maximal sequence of
  consecutive glyphs in the same font on the same `rawdict` line, joined in
  extraction order — exactly as R does.
- **UP-CV-2** One converter instance per document, runs fed in page/line order.
  (Some converters are stateful across runs: `sakal` keeps the glyph numbering
  of the previous line.) State is reset between documents.
- **UP-CV-3** The converted text of every run must equal what the unmodified
  indic2unicode converter returns for the same input string. This is the
  parity invariant; §7 tests it.
- **UP-CV-4** Characters a converter drops (no token) are reported as issues
  `unconverted_char` with code point, font, page and bbox — today they are
  only logged.
- **UP-CV-5** Converter exceptions are caught per run: the run's raw text is
  output, an issue `converter_error` is raised, processing continues.

### 5.6 Provenance and alignment (the new capability)

Converters reorder (matra-i, reph), merge (compose rules), split (one glyph →
several tokens) and drop characters, so output characters do not line up 1:1
with glyphs. To give boxes for converted text, unipdf tracks provenance.

- **UP-AL-1** The converter pipeline gains an **additive** provenance mode:
  every token carries the set of source character indices it came from:
  - lexing: the token's `lexpos .. lexpos+len(value)`;
  - `multiple_tokens` expansion: each produced token inherits the full span;
  - `compose_tokens`: the replacement inherits the union of what it replaced;
  - `jump_before_tokens` / `jump_after_tokens`: tokens move with their sets;
  - `tokens_to_unicode`: each output substring is tagged with its token's set.
- **UP-AL-2** Converters that transform the string before lexing must map
  indices through that step. Known cases in scope:
  `chanakya` (deletes ZWJ/ZWNJ), `sakal` (1:1 substitution — identity map),
  `arialuni_glyphs` and its subclasses (splits by script and concatenates),
  `abhishek` (own token pipeline: drops `SPACER` and shared tokens).
  *[M0]* chanakya, sakal and the ArialUniGlyphs family are done in the
  prototype and give identical text. abhishek is still pending. Inside
  `arialuni_glyphs`/`nirmalaui_glyphs`, segments in other scripts are
  run-level (out of scope, D-6).
  A converter that cannot provide a map declares so, and its runs fall back to
  run-level provenance (UP-AL-5).
- **UP-AL-3** Provenance mode must not change converted text: for every input,
  `to_unicode(s) == to_unicode_with_provenance(s).text`. Verified over the
  whole `testdata/` and the PDF corpus.
- **UP-AL-4** Source character indices map to glyphs (a glyph with a
  multi-code-point text owns all its indices), so every output substring maps
  to a set of glyphs and therefore to a bbox (union).
- **UP-AL-5** Granularity guarantees, from strongest to weakest:
  - **word** boxes are always provided and correct;
  - **akshara/cluster** boxes are provided where provenance is available;
  - **per-character** boxes are not promised: a matra or halant can have no
    glyph of its own.
  Each box states which level it is.
- **UP-AL-6** Words are formed **after** conversion: the converted run text
  is split on whitespace, and each word's glyph set is the union of its
  characters' provenance. Converting word by word is not allowed (it changes
  output: reph and matra-i movement is per run).
- **UP-AL-7** *[M0]* Some input characters produce no output: lexer-skipped
  codes such as surekh `ò þ ú ù`, and aryan2's `t_ignore`. Their glyphs belong
  to no output character. They are attached by geometry to the word whose box
  contains or is nearest to them, flagged `unattributed`, and still count
  toward that word's box.

### 5.7 Layout

MuPDF's `rawdict` "lines" are not visual lines. On
`202606122029536001.pdf`, of 175 consecutive line pairs inside a block, 154
sit on the same baseline: MuPDF starts a new line wherever a justified gap is
wide, so `डेअरी फार्म, मांजरी, पुणे येथील` arrives as five one-word lines
(cidpdf kept it as one). Conversion must still run on `rawdict` lines (that
is what R does), so layout has two levels.

- **UP-LY-1** **Conversion units** are `rawdict` lines, unchanged (UP-CV-1).
- **UP-LY-2** **Output lines** are visual rows: consecutive `rawdict` lines of
  the same block, same writing direction, whose baselines differ by at most
  a tolerance (initially 0.2 × font size; tuned in M2), merged left to right.
  A merge joins with one space and never re-runs conversion.
- **UP-LY-3** A line's bbox is the union of its words' boxes (not MuPDF's line
  box, which includes generated spaces); a block's is the union of its lines'.
- **UP-LY-4** Words are the converted text split on whitespace (UP-AL-6), then
  joined by UP-LY-5. A word never spans two output lines.
- **UP-LY-5** **Word joining** (D-12). A space between two words is removed
  when either holds:
  - **J1 (script rule)** the following word starts with a character that
    cannot begin a Devanagari word: a dependent vowel sign, virama, nukta,
    anusvara, chandrabindu or visarga (U+0900–0903, U+093A–094F,
    U+0951–0957, U+0962–0963). Safe in all cases.
  - **J2 (geometry rule)** the space is one MuPDF generated (`synthetic`) and
    the gap between the two glyphs is below a threshold relative to font size
    (initially 0.15 × size; tuned on the corpus in M2). A space that is a real
    glyph in the PDF is **never** removed by J2.
  Each join is recorded on the word (`joined_from: [w1, w2]`, `join_rule`) and
  as an issue `joined_words`. `--no-join` gives the unjoined words.
- **UP-LY-6** Measured on `202606122029536001.pdf`: every space in it is a
  real glyph (none `synthetic`), and R keeps `फुले` whole all 46 times. The
  `फु ले` split seen earlier came from cidpdf's gap-based word splitting, which
  is not carried over. J2 is aimed at the `रे लवे` case of indic2unicode's
  README; the M2 corpus must contain such a document, or J2 is left disabled.
- **UP-LY-7** Reading order: pages in order; rows top-to-bottom in MuPDF block
  order; no column detection in v1.

### 5.8 Attributes

- **UP-AT-1** Word font size = the most common glyph size; all distinct sizes
  are also kept.
- **UP-AT-2** Bold is the OR of evidence, each recorded as a string as cidpdf
  does: font name keyword; PDF descriptor `FontWeight` ≥ 600; OS/2
  `usWeightClass` ≥ 600; OS/2 `fsSelection` bold bit; render mode 1/2
  (stroke / fill+stroke); over-print duplicates and fill+stroke repeated
  passes (UP-EX-3), with line width (*[M0]* Word's synthetic bold is a
  stroke of `size / 35`). *[M0]* MuPDF's `char_flags` bit 8 is **not**
  evidence: it is set exactly when the font name is bold.
- **UP-AT-3** Italic: font name contains italic/oblique, or descriptor
  `ItalicAngle` ≠ 0, or OS/2/head italic bits; evidence recorded.
- **UP-AT-4** A word whose glyphs disagree on an attribute reports it per font
  run (cidpdf's `font_runs`) and a word-level value (bold if any run is bold —
  cidpdf's rule; size by majority).
- **UP-AT-5** No attribute changes text. In particular cidpdf's ASCII→Devanagari
  digit remap for companion fonts is **not** carried over (it violates D-7).

### 5.9 Document model

Absorbed from cidpdf and adapted. Coordinates are PDF points, **top-left
origin** (PyMuPDF's), `(x0, y0, x1, y1)`; cidpdf's ×1000 bottom-left
`(x, y, w, h)` boxes are dropped.

```
Document
  source (filename, sha256, size), pages[], fonts[], issues[]
Page
  index, width, height, rotation, lines[], words[], glyphs[]
Line
  index, bbox, text, words[]
Word
  index, line_index, text, bbox, bbox_level ("word"),
  clusters[]: (text, bbox, glyph_ids[])      # where provenance exists
  font_runs[]: (font_id, text, raw_text, bbox, size, bold, bold_evidence[])
  size, sizes[], bold, bold_evidence[], italic, italic_evidence[], issue_ids[]
Glyph
  index, text, glyph_id, origin, bbox, font_id, size, render_mode,
  color, opacity, synthetic, invisible, overprinted, seqno
Font
  id, pdf_name, base_name, xref, type, encoding, embedded, has_tounicode,
  repaired, repaired_as, converter, resolution_rule,
  names{family, subfamily, full_name, postscript_name, version},
  weight, italic_angle, bold_evidence[], italic_evidence[]
Issue
  id, severity, code, message, page, font_id, bbox, context
```

- **UP-MD-1** Every word keeps both converted `text` and the pre-conversion
  `raw_text` of its runs, and the glyph ids behind it; both are in the default
  JSON (D-13).
- **UP-MD-2** Model serialises to JSON with a `schema_version`; JSON output is
  deterministic (stable ordering, no timestamps by default).

### 5.10 API and CLI

- **UP-API-1** Library entry point:
  ```python
  import unipdf
  doc = unipdf.open("in.pdf", pages=[0, 1], repair=True, fonts={"X": "chanakya"})
  doc.text()                 # == reference pipeline text
  for w in doc.iter_words(): w.text, w.bbox, w.bold, w.size
  doc.to_json()
  ```
- **UP-API-2** `unipdf.convert(fontname, text)` keeps indic2unicode's string API
  for non-PDF use, plus `convert_with_provenance`.
- **UP-CLI-1** Commands (cidpdf's filter pattern, renamed):
  - `unipdf text` — text, page separator `--- Page Break ---` (as `read_pdf.py`)
  - `unipdf words` — TSV/JSON: page, line, word, x0 y0 x1 y1, font, size, bold, italic, text
  - `unipdf glyphs` — one row per glyph incl. glyph id and raw text
  - `unipdf json` — the full model
  - `unipdf fonts` — font table incl. repaired / converter / resolution rule
  Common flags: `-p/--pages`, `-o/--output`, `--no-repair`, `--font`,
  `--font-map`, `--no-join` (UP-LY-5), `--rawdict-lines` (output lines =
  `rawdict` lines, no row merge; with `--no-join` this is R, UP-VF-4a), `-v`.
- **UP-CLI-2** Missing conversions are summarised on stderr (as
  `read_pdf_cidpdf.py` does); exit status is non-zero only for real errors.
- **UP-CLI-3** A visual overlay command (`unipdf show`: page image with word
  boxes and text) — ported from cidpdf's `visualize_pdf` — for checking geometry.

### 5.11 Issues and logging

- **UP-IS-1** cidpdf's `IssueBag` model is kept; codes in v1 include
  `no_text_layer`, `repair_failed`, `no_converter`, `unconverted_char`,
  `converter_error`, `provenance_unavailable`, `joined_words`.
- **UP-IS-2** Library code never prints; it logs (`logging`) and records issues.

---

## 6. What is absorbed, ported or dropped

| Source | Fate in unipdf | Notes |
|---|---|---|
| `indic2unicode/fonts/basefont.py` | Absorbed, extended | Provenance mode added (UP-AL-1); default path unchanged |
| `indic2unicode/fonts/{hindi,marathi,glyphs}/`, `langs/devanagari.py`, `langs/marathi.py`, `langs/baselang.py` | Absorbed unchanged except pre-pass index maps (UP-AL-2) | |
| `indic2unicode/fontconv.py` | Absorbed | Registry becomes the input to UP-FN-2 |
| `indic2unicode/tools/fix_tounicode.py` | Absorbed unchanged | 3.8k lines, mostly tables; all scripts kept (D-9) |
| `indic2unicode/testdata`, `expected`, `regression.py` | Absorbed as the converter test suite | Must keep passing unchanged (§7.1) |
| Other-script converters, `langs/` of other scripts, their `testdata`/`expected` | Absorbed unchanged, unsupported (D-9) | Their regression files still run in UP-VF-1 as a smoke test, not a gate |
| `indic2unicode/tools/pdf_ocr.py` | Dropped | |
| `cidpdf` data model, `IssueBag`, bbox union, font metadata via fontTools, bold/italic evidence | Ported onto PyMuPDF glyphs | |
| `cidpdf` `Pypdfium2LayoutEngine` | Replaced by `rawdict` grouping | |
| `cidpdf` `VisualRowLayoutEngine` | Dropped (D-11) | |
| `cidpdf` CLI filters, `visualize_pdf` | Ported (UP-CLI-1, -3) | |
| `cidpdf` `CMapRepository`, YAML `cmaps/`, `DevanagariCidConverter`, glyph SHA candidates, `_GlyphRenderer`, digit remap, docling backend/sidecar, cmap-tool workflow | Dropped | D-1, D-3, D-7 |
| `read_pdf.py`, `read_pdf_cidpdf.py` | Superseded | `read_pdf.py` becomes the basis of R (§7.2) with its two resolver bugs fixed |

---

## 7. Verification

### 7.1 Converter regression (absorbed as is)

- **UP-VF-1** `regression.py` over `testdata/` → `expected/` passes for every
  Devanagari font with zero diffs, before and after absorption (gate). The
  other scripts' files run too, as a smoke test that absorption broke nothing
  (D-9); a diff there is reported, not a release blocker.
- **UP-VF-2** For every Devanagari test file, provenance mode yields identical
  text (UP-AL-3).

### 7.2 PDF parity gate

The reference pipeline **R** is indic2unicode as used today, made precise:
PyMuPDF open → `fix_document` → `rawdict` → per line, consecutive spans of the
same font joined → converter chosen by UP-FN-2 → `FontConv.to_unicode` → lines
joined with `\n`, blocks with `\n\n`. (This is `read_pdf.py` with its
`*_glyphs`-on-unrepaired-font and prefix-match bugs fixed.)

- **UP-VF-3** A corpus of Hindi/Marathi PDFs is assembled from `~/orgpedia`
  (e.g. `mah2024/.../documents/`, `CID_Glyphs/`, `Try/playa/`), covering every
  in-scope converter at least once, plus scanned and mixed-script files.
  Golden text = R's output, stored with the corpus.
- **UP-VF-4** Release gate, for every corpus PDF and page:
  1. every conversion run's text equals R's for the same run, exactly
     (UP-CV-3);
  2. the page's word sequence equals R's word sequence (R's text split on
     whitespace) after applying unipdf's recorded joins to R — i.e. the only
     differences allowed are whitespace, and joins listed in `joined_words`.
  Line breaks may differ from R (visual rows, UP-LY-2); words may not.
- **UP-VF-4a** `unipdf text --no-join --rawdict-lines` reproduces R's text
  byte for byte, so R itself stays checkable.

### 7.3 Geometry and attributes

- **UP-VF-5** Invariants on every corpus page: every word bbox lies inside the
  page; every non-synthetic glyph belongs to exactly one word; a word's bbox is
  the union of its glyphs' boxes; cluster boxes lie inside their word box.
- **UP-VF-6** A hand-checked set (~50 words across fonts, incl. reph,
  matra-i and conjunct cases) with expected word and cluster boxes.
- **UP-VF-7** Bold/italic labels checked on a small hand-labelled set covering
  each evidence type (bold font, stroke render mode, over-print).

---

## 8. Non-functional requirements

- **UP-NF-1** Python ≥ 3.12. Dependencies: `pymupdf`, `ply`, `fonttools`
  (`pillow` only for `unipdf show`). No platform-specific custom wheels.
- **UP-NF-2** Deterministic: same input and options → byte-identical output.
- **UP-NF-3** Performance: `unipdf text` within 1.5× of R on the corpus;
  provenance/geometry adds at most 2× over `unipdf text`.
- **UP-NF-4** Memory proportional to one page plus document fonts; pages are
  processed one at a time.
- **UP-NF-5** Packaging: one `uv`-managed project at `Try/indic2unicode/unipdf/`
  (D-10) with `src/unipdf/`, `specs/`, tests under `tests/`, console script
  `unipdf`. It does not import from the sibling `indic2unicode/` or `cidpdf/`
  directories at runtime (D-5); those stay as the upstream copies the code was
  absorbed from.

---

## 9. Milestones

| M | Content | Exit criterion |
|---|---|---|
| M0 | Spike: join texttrace ↔ rawdict per glyph; provenance through `BaseFont` for `chanakya`, `arialuni_glyphs`, `sakal` | Joins exact on corpus sample; UP-AL-3 holds for those three |
| M1 | Absorb indic2unicode; R implemented; `unipdf text` | UP-VF-1, UP-VF-4 |
| M2 | Glyph model, words, bboxes, provenance for all in-scope converters | UP-VF-2, UP-VF-5, UP-VF-6 |
| M3 | Font records, attributes | UP-VF-7 |
| M4 | CLI, JSON schema, `show` | UP-CLI-* |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| texttrace and rawdict disagree on glyph identity/order for some producers, breaking the join | M0 spike on the corpus; rawdict text always wins (UP-EX-2), texttrace only adds attributes |
| A converter's pre-pass cannot be index-mapped | Run-level fallback (UP-AL-2/5); word boxes still correct |
| PyMuPDF version changes extraction and silently changes text | Pin PyMuPDF version; parity gate (UP-VF-4) runs on every upgrade |
| Stateful converters (`sakal`) depend on run order | UP-CV-2; corpus includes multi-numbering Sakal documents |
| Absorbing means two copies of indic2unicode drift | Absorb once; upstream changes are ported deliberately, re-running §7 |

---

## 11. Open questions

Resolved: OQ-1 → D-8, OQ-2 → D-9, OQ-3 → D-10, OQ-4 → D-11, OQ-5 → D-14,
OQ-6 → D-12, OQ-7 → D-13.

**OQ-8 → D-17** (decided 2026-10-16: option (a) for v1, input adapters later). *[M0]* Legacy 8-bit fonts named `DVB-TTSurekh`, `DVB-TTSurekhEN`,
`DVB-TTYogesh` (and their `,Bold` / `+1` variants) occur in the corpus. No
UP-FN-2 rule resolves them: FontConv's keys are `surekh`, `yogesh`,
`DVBWTTYogeshNormal`. So R, and therefore unipdf under D-7, outputs their
text unconverted. Options:
(a) keep parity; users pass `--font-map DVB-TTSurekh=surekh`;
(b) add these names as resolution aliases. This changes output relative to R
for those fonts only, and the parity gate would exempt them as a recorded
departure, like D-12.
Recommendation: **(a) for v1**. A spot check on `20040812163004001.pdf`
shows `yogesh` on PyMuPDF's text is only partly right (`महाराष्ट्र शासा`
for `शासन`, `विभाा` for `विभाग`). PyMuPDF delivers some bytes as other
characters (e.g. U+2212) than the converter's testdata uses, so a plain alias
would produce plausible but wrong text. (b) needs an input-mapping adapter
per font and a corpus check; it is a post-v1 item.
**OQ-9** *[M1]* `/ActualText` and converters. In an ActualText span PyMuPDF
returns the replacement text, which is already logical-order Unicode (UP-EX-7).
R still runs the font's converter over it. For a repaired font that means a
reordering pass over correct text: Google Docs `Hindi-Google.pdf` comes out
`हंिदी` (read_pdf.py gives the same). Ignoring ActualText fixes that file but
breaks the Word Nirmala UI export, whose glyphs have no usable Unicode
(`पिʮम`). Options:
(a) keep R's behaviour;
(b) characters from ActualText bypass the converter. The D-15 join
identifies them. This is a recorded departure from R, like D-12, and the
parity gate exempts runs that contain ActualText.
Recommendation: (b), implemented in M2. Until then the affected goldens are
marked `known_bad` in the corpus manifest.
New questions get the next number (OQ-10).

