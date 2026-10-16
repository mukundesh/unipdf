# unipdf — M0 spike results

Date: 2026-10-15. Plan: IMPLEMENTATION_PLAN.md §2 M0. Scripts, corpus list and
overlays: `unipdf/spikes/m0/` (run with a Python that has pymupdf 1.28.2, ply,
fontTools; paths to `indic2unicode/` are absolute).

**Verdict: all three spikes pass.** The design stands. Amendments to
REQUIREMENTS (Draft 4) are listed at the end of each section and in §4.

## 0. Spike corpus

19 PDFs (`spikes/m0/corpus.txt`), picked by `survey.py` from a font survey of
up to 350 PDFs sampled (25 per directory) across `~/orgpedia` (mahfin, mah2024, mahGRs, pmccirc,
indicGovBench, hindi_docs, CID_Glyphs, playa):

| Converter (after repair) | PDFs in survey sample | In spike corpus |
|---|---|---|
| `sakal` | 122 | 4 + most of the others carry it too |
| `mangal_glyphs` | 33 | 3 |
| `arialuni_glyphs` | 16 | 3 |
| `nirmalaui_glyphs` | 15 | 3 |
| `dvotsurekh` | 11 | 3 |
| legacy 8-bit `DVB-TTSurekh` / `DVB-TTYogesh` | up to 5 | 2 |
| plus the sample PDF and two Hindi Word/Google exports | | 3 |

No chanakya/krutidev/devlys PDFs turned up in the sample; those converters are
covered by `testdata/` only. Finding for UP-FN: **`DVB-TTSurekh`,
`DVB-TTSurekhEN`, `DVB-TTYogesh` are not resolved by any rule** (FontConv keys
are `DVBWTTYogeshNormal`, `surekh`, `yogesh`), so R leaves their text raw.
Forcing `yogesh` on `20040812163004001.pdf` is only partly right
(`महाराष्ट्र शासा` for `शासन`): PyMuPDF delivers some bytes as other characters
(e.g. U+2212) than the converter expects. See OQ-8.

Pages: first 8 per PDF for S1, all pages for S2, first 5 for S3.
96,981 `rawdict` characters, 106,411 `texttrace` entries, 11,594 words.

## 1. S1 — joining `rawdict` characters to `texttrace` glyphs

**Result: 99.971 % joined (96,932 of 96,960 non-synthetic characters). Pass
(≥ 99.9 %). All 28 misses are inside `/ActualText` spans.**

### 1.1 Why a join by origin fails (first attempt: 90.0 %)

The two outputs place three kinds of character differently
(`202606122029536001.pdf` p1, `ामा फुल`):

| Case | `texttrace` | `rawdict` |
|---|---|---|
| Extra code points of a multi-code-point glyph (`त्` is one glyph) | `्` with `gid = -1` **at the glyph's origin** | `्` at the glyph's **end** (origin + advance), zero-width box |
| Zero-advance mark (`ु`, gid 126) | true pen position 408.87 | moved to the end of the previous glyph, 412.27, zero-width box |
| Fill + stroke text (Sakal, DVOT headings) | the span twice: `type 0` then `type 1`, identical glyphs | once |

### 1.2 The join that works (`s1_join.py`)

1. Drop `texttrace` spans that repeat an earlier span glyph for glyph (same
   unicode, gid, origin); remember on the original span which render types
   repeated it.
2. Walk `rawdict` characters in order with a cursor into the `texttrace`
   entries. For each non-synthetic character, in order of preference:
   1. the next unused entry, if its unicode matches and either its origin
      matches (± 0.01 pt) **or it is a continuation (`gid = -1`)**;
   2. an unused entry with the same unicode at the same origin;
   3. the next unused entry with the same unicode (sequence only);
   4. the same unicode within the next 8 unused entries (reordered glyphs);
   5. an entry at the same origin whose unicode is U+FFFD (see 1.4).

Joined by: sequence + origin 87,102; sequence only 9,795 (6,243 continuation
code points, 3,552 moved zero-advance marks, of which 550 moved ≥ 1 pt);
origin only 12; lookahead 6; U+FFFD 17. Preferring sequence for continuations
matters: matching `प्र`'s `्` by origin takes the `्` of the next glyph `क्ष`
at the same x, and the chain breaks.

### 1.3 Misses: `/ActualText`

28 misses, in `order_en_current_021.pdf` (Word export, Nirmala UI) and
`Hindi-Google.pdf`. Both use `/ActualText`; `rawdict` (flags 199, as R uses)
reports the ActualText (`पश्चिम`) over glyphs that draw `प ि <gid 686> म`. With
`TEXT_IGNORE_ACTUALTEXT` `rawdict` and `texttrace` agree. There is no 1:1
glyph for these characters; it is not a join defect. R uses ActualText, so
unipdf must keep it (UP-EX-2).

### 1.4 Other observations

- For a glyph with no Unicode, `rawdict` gives the glyph id as a character
  (`ʮ` = U+02AE = gid 686, the input some converters expect) while
  `texttrace` gives U+FFFD. Text always comes from `rawdict` (UP-EX-2).
- 87 `texttrace` spaces and 12 other entries have no `rawdict` character
  (trailing spaces MuPDF trims; the ActualText glyphs).
- `char_flags` bits seen: 16 FILLED (all), 8 BOLD, 128 UNICODE_IS_CID,
  512 SYNTHETIC_LARGE. Never 32 STROKED.

### 1.5 Bold evidence (`s1_bold.py`)

- **`char_flags & 8` adds nothing**: it is set exactly on the characters whose
  font *name* is bold (`flags & 16`), in every PDF. MuPDF does not detect fake
  bold here.
- **The fill + stroke copy is the fake bold**: 9,380 glyphs in 13 of 19 PDFs
  (Sakal and DVOT documents: `शासन`, `महाराष्ट्र`, headings). The stroke
  line width is `size / 35` in every case (0.343 at 12 pt, 0.315 at 11 pt,
  0.285 at 10 pt), which is Word's synthetic bold. None of these fonts has a
  bold name, so **without the join this bold is invisible**.

### 1.6 Amendments

- UP-EX-1: the glyph record is built by this join; its origin comes from
  `texttrace` (true pen position), its box from `rawdict` (D-14).
- UP-EX-3: answered. `texttrace` exposes the copies; `rawdict` merges them.
- UP-EX-4: a glyph's continuation code points are the `gid = -1` entries that
  follow it in `texttrace`; they are merged into the one record.
- New UP-EX-7: ActualText spans.
- UP-AT-2: drop "`char_flags` fake-bold bit"; add "fill+stroke copy
  (`texttrace` type 1 repeating type 0), with its line width".

## 2. S2 — provenance through the converters

**Result: tracked text == `to_unicode` text on 100 % of inputs; every output
character has at least one source index. Pass.**

Prototype: `spikes/m0/tracked.py` (≈ 190 lines). It does **not** edit
indic2unicode. It runs BaseFont's passes as functions over
`(token, sources)` pairs on an unmodified converter instance, with
pre-pass adapters for `chanakya`, `sakal` and `ArialUniGlyphs` (therefore also
`mangal_glyphs`, `nirmalaui_glyphs`). Source span of a token =
`range(tok.lexpos, lexer.lexpos)` (also correct for LITERAL tokens returned by
`t_error`).

| Input | Runs | Mismatches |
|---|---|---|
| `testdata/` of 12 Devanagari converters, whole file per call | 12 | 0 |
| the same, one line per call (state carried, as in a PDF) | 168,097 | 0 |
| Corpus runs, R's grouping (`sakal` 17,040; `nirmalaui_glyphs` 733; `arialuni_glyphs` 212; `dvotsurekh` 83; `mangal_glyphs` 18) | 18,086 (229k chars) | 0 |

Granularity: largest source set of one output piece is 1–6 characters for
every adapted converter on Devanagari. Coarse (run-level) provenance remains
for:

- `abhishek` (own token pipeline; no adapter yet; no corpus PDF uses it);
- non-Devanagari segments inside `arialuni_glyphs`/`nirmalaui_glyphs`
  (Kannada/Odia/Telugu/Malayalam passes); out of scope (D-6).

Input characters with **no** output, so no provenance: lexer-skipped codes,
e.g. surekh `ò þ ú ù` (62k in its testdata) and aryan2 `t_ignore` `ó ô`
(3.2k). Their glyphs belong to no output character; they must be placed by
geometry.

Cost: tracked/plain time ×1.04–1.13 (sakal, dvotsurekh, surekh,
mangal_glyphs); ×3 for chanakya (0.03 s → 0.10 s on 5k chars).

### 2.1 Decision for IMPLEMENTATION_PLAN §3

Take the "separate" option, in its strongest form: **the absorbed
indic2unicode code stays byte-for-byte unchanged** (only the import rewrite),
and provenance lives in `unipdf/convert/provenance.py` as `tracked.py` does,
operating on converter instances. unipdf converts only through the tracked
path; `test_provenance_equivalence.py` pins it to `to_unicode` over
`testdata/` and the corpus. The adapter registry only applies an adapter when
the class's `to_unicode` is the one it was written for, so a converter that
overrides `to_unicode` without an adapter falls back to run-level provenance
automatically, never to wrong provenance.

### 2.2 Amendments

- UP-AL-1/2: confirmed; adapters for chanakya, sakal, ArialUniGlyphs family
  done in prototype; abhishek pending (M3).
- New UP-AL-7: dropped input characters.

## 3. S3 — are `rawdict` character boxes good enough for words? (D-14)

**Result: yes. D-14 stands.**

Method (`s3.py`): word = run of non-space `rawdict` characters on a `rawdict`
line; box A = union of `rawdict` char boxes. Reference: ink box K = union of
the glyphs' outline bounds, read with fontTools from the embedded font, using
the glyph ids from the S1 join and the `texttrace` origin and size. Plus
overlays at 150 dpi (`ov_sakal.png`, `ov_dvot.png`, `ov_nirmala.png`; red =
A, blue = K).

9,559 words had an ink box:

| Measure | Result |
|---|---|
| Ink above A by > 0.05 em | **0** |
| Ink below A by > 0.05 em | **0** |
| Ink left / right of A by > 0.05 em | 236 / 187 words (220 / 140 of them in one DVOT-Surekh PDF) |
| Ink area inside A ≥ 98 % | 95.7 % of words |
| Ink area inside A ≥ 90 % | 99.7 % of words |
| A taller than ink | 0.62 em on average (ascender + descender box) |
| Vertically stacked word pairs (different lines) whose A boxes overlap > 20 % | 3 of 1,297 |

Matras, reph, conjuncts and lower marks are always inside A. The horizontal
spill is ≤ ~0.12 em (≈ 1.5 pt at 12 pt). It comes from glyph ink wider than
the advance (DVOT) and from zero-advance halants (`स्`, `धव्`) that hang past
the word's last advance. The overlays show A enclosing every word in all
three families.

### 3.1 Font identity gap (affects UP-FN-1 and any ink box)

Neither `texttrace` nor `rawdict` gives a span's font **xref**, only its name.
On `202606122029536001.pdf` page 1 three fonts are named `Sakal Marathi`
(one Type0/Identity-H, two TrueType/WinAnsi). That is why 2,035 words got no
ink box: the glyph id was looked up in the wrong program. Converters only
need the name (R does the same), so text is unaffected; per-font metadata and
ink boxes are.

### 3.2 Amendments

- D-14: confirmed by S3; record the numbers. The ink box becomes an optional
  later extension (`--tight-boxes`), not v1, and needs a span → xref mapping.
- New UP-FN-6: font records are keyed by name; same-name fonts are listed
  together.

## 4. Changes to the plan

- M2 now starts from `s1_join.py` (the join) and M3 from `tracked.py`
  (provenance). Both are prototypes with known pass rates, not open
  questions.
- IMPLEMENTATION_PLAN §3: decided as in 2.1.
- New open question OQ-8 (legacy `DVB-TT*` names), REQUIREMENTS §11.
