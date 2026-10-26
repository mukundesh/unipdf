# unipdf JSON, schema 0.2

What `unipdf json` and `Document.to_json()` / `to_dict()` give. For how to
use it - which fields a pipeline needs, recipes, a full example - see
[`docs/USAGE.md`](../docs/USAGE.md). The field tables below are checked
against the output by `tests/test_json.py`: every field listed is emitted and
every field emitted is listed.

## Conventions

- **Coordinates** are PDF points (1/72 inch) with the origin at the **top
  left** of the page **as it is displayed**, y growing downwards: the space
  of `width` × `height` and of the page's rendered image, rotated pages
  included. A box is `[x0, y0, x1, y1]`, a point `[x, y]`. Numbers are
  rounded to 3 decimals.
- **Indices** are **0-based** and **per page**: a word's `glyphs` are
  positions in its page's `glyphs`, a line's `words` positions in its page's
  `words`. (The tables of the `words`, `glyphs` and `regions` commands
  number from 1.)
- **Fonts** are named as PyMuPDF names them: the PDF's font name without the
  six-letter subset prefix (`ABCDEE+Mangal` → `Mangal`). `fonts[].name` is
  the key the other objects use.
- **Output is deterministic**: no timestamps, stable order. `source.filename`
  is the path as given.
- **Text**: `text` is Unicode in logical order. `raw_text` (`raw` in runs) is
  what the PDF itself gives for the glyphs, after unipdf has repaired broken
  font maps but before a converter has put the text in order - kept so that
  a wrong conversion can be checked against what was on the page.
- **Legacy 8-bit fonts** (DVB-TTSurekh, Kruti Dev, …) are not read. Their
  words have `text` `""` and a `region`; a line's `text` holds `⟦8bit:N⟧` in
  place of the region, N being the region's `index` + 1 (the number
  `unipdf regions` gives it).
- **`--no-glyphs`** (`to_dict(glyphs=False)`) leaves out every page's
  `glyphs` and `runs`, most of the size. The glyph numbers in words, lines
  and regions are still given and still refer to the full model.

## Terms

- **Glyph**: one shape drawn on the page. A conjunct like क्ष can be one
  glyph; ि is drawn before its consonant, so glyph order is not text order.
- **Block, PyMuPDF line**: PyMuPDF's own grouping of the text it extracts
  (its `rawdict` output). unipdf converts text one PyMuPDF line at a time
  and merges PyMuPDF lines on the same baseline into its output lines.
- **Run**: consecutive glyphs of one font on one PyMuPDF line - the unit a
  converter turns into Unicode.
- **Converter**: an indic2unicode module that turns a font's text into
  Unicode in logical order (`sakal`, `mangal_glyphs`, …).
- **Repair**: before extraction, unipdf rewrites the ToUnicode map (the
  PDF's table from glyph to character) of fonts known to carry a broken one.
- **ActualText**: replacement text a PDF can put over glyphs. unipdf uses it
  unless it is known to be wrong (it holds U+FFFD, or its font was
  repaired); then the glyphs are read instead.
- **Akshara / cluster**: a consonant with its conjoined consonants and signs
  (हिं, क्ष्म), the unit a word's `clusters` give boxes for.

## Document

| field | type | meaning |
|---|---|---|
| `schema_version` | string | `"0.2"` |
| `source` | object | `filename` (null when read from bytes), `sha256`, `size` (bytes) |
| `options` | object | the `unipdf.open()` arguments in effect: `pages` (null = all), `repair`, `force`, `font_map`, `join`, `rawdict_lines`, `j2`, `actual_text` (`"bypass"`/`"convert"`), `row_tolerance`, `legacy` (`"skip"`/`"keep"`) |
| `pages` | [Page] | the pages read, in order |
| `fonts` | [Font] | one per font name met on those pages |
| `issues` | [Issue] | what could not be done, in the order met |
| `repaired` | object or null | font name → the name the repair treated it as; null when repair did not run or failed |

## Page

| field | type | meaning |
|---|---|---|
| `index` | int | 0-based page number in the PDF |
| `width`, `height` | number | page size in points, after rotation (what coordinates are relative to) |
| `rotation` | int | the page's `/Rotate` |
| `blocks` | [int] | PyMuPDF block numbers that hold text, in output order |
| `lines` | [Line] | output lines: one per visual row (default), or one per PyMuPDF line with `rawdict_lines` |
| `words` | [Word] | in reading order |
| `runs` | [Run] | conversion units (left out with `--no-glyphs`) |
| `glyphs` | [Glyph] | every glyph of the page, in PyMuPDF's order (left out with `--no-glyphs`) |
| `legacy_regions` | [LegacyRegion] | words in legacy 8-bit fonts, left out of the text |

## Line

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `block` | int | the PyMuPDF block it belongs to |
| `bbox` | box or null | union of its words' boxes |
| `text` | string | as `unipdf text` prints it, with a placeholder for each legacy region |
| `words` | [int] | its words |
| `sources` | [[int, int]] | `(block, line)` of the PyMuPDF lines merged into it |

## Word

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `line` | int | its line |
| `text` | string | Unicode text; `""` in a legacy region |
| `raw_text` | string | the PDF's text for its glyphs, before conversion |
| `bbox` | box or null | union of the boxes of its glyphs, spaces left out |
| `glyphs` | [int] | the glyphs its text came from, and its `unattributed` glyphs, in PyMuPDF's order |
| `glyph_ids` | [int] | the font's glyph ids for those glyphs; an ActualText group gives the ids of the glyphs it stands for, so the list can be longer than `glyphs` |
| `fonts` | [string] | fonts of its glyphs, in order of first use |
| `size` | number or null | most common font size of its glyphs |
| `sizes` | [number] | all its font sizes, ascending |
| `bbox_level` | string | `"word"` |
| `joined_from` | [string] or null | the parts PyMuPDF split it into, when unipdf joined them |
| `join_rules` | [string] or null | why each space was removed: `"J1"` (the next part starts with a vowel sign or other mark no word starts with), `"J2"` (a narrow space PyMuPDF made up; off by default) |
| `unattributed` | [int] | glyphs the converter dropped, given to the nearest word: in `glyphs`, `raw_text` and `bbox`, not in `text` |
| `clusters` | [Cluster] or null | aksharas with boxes; null when its converter gives no per-glyph mapping, or in a legacy region |
| `font_runs` | [FontRun] | the parts of the word in one font |
| `bold`, `italic` | bool | bold if any font run is; italic likewise |
| `bold_evidence`, `italic_evidence` | [string] | the evidence of the runs that decided (see Evidence) |
| `region` | int or null | the legacy region it is in: one of its glyphs, not a space, is in a legacy 8-bit font |

## LegacyRegion

Consecutive words of a line in legacy 8-bit fonts, for another tool (OCR) to
read from the page image.

| field | type | meaning |
|---|---|---|
| `index` | int | per page; the text's placeholder is `⟦8bit:index+1⟧` |
| `line` | int | its line |
| `bbox` | box or null | union of its words' boxes |
| `fonts` | [string] | its legacy fonts, in order of first use |
| `words` | [int] | its words, consecutive |
| `raw_text` | string | its words' `raw_text`, joined by spaces |

## Cluster

| field | type | meaning |
|---|---|---|
| `text` | string | one akshara |
| `bbox` | box or null | union of its glyphs' boxes |
| `glyphs` | [int] | the glyphs it came from |

## FontRun

| field | type | meaning |
|---|---|---|
| `font` | string | |
| `text`, `raw_text` | string | |
| `bbox` | box or null | |
| `glyphs` | [int] | |
| `size` | number or null | most common font size |
| `bold`, `italic` | bool | |
| `bold_evidence`, `italic_evidence` | [string] | |

## Run

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `block`, `line` | int | its PyMuPDF line |
| `font` | string | |
| `converter` | string or null | indic2unicode converter used; null = text passed through as the PDF gives it |
| `rule` | int or string | why that converter: 1 the font was repaired, 2 a converter that reads the font repaired or not, 3 by font name, 4 none, `"forced"` (`--font` / `--font-map`), `"legacy"` (a legacy 8-bit font, left out) |
| `raw` | string | the glyphs' text before conversion |
| `text` | string | converted text |
| `glyphs` | [int] | |
| `pieces` | [[string, [int]]] | each piece of `text` with the glyphs it came from |
| `actual_text` | bool | holds ActualText glyphs, which bypass the converter |
| `provenance` | string | `"piece"`, or `"run"` when every piece comes from the whole run |
| `logical` | bool | `text` is known to be in logical order |
| `error` | string or null | the converter's exception; `text` is then `raw` |

## Glyph

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `text` | string | the PDF's text for it, after repair (may be several code points) |
| `glyph_id` | int or null | the font's glyph id; null for ActualText groups and glyphs PyMuPDF gave no id for |
| `origin` | point | pen position (on the baseline) |
| `bbox` | box | from the font's ascender to its descender, not the ink |
| `font` | string | |
| `size` | number | |
| `block`, `line` | int | its PyMuPDF line |
| `render_mode` | int or null | 0 fill, 1 stroke, 2 fill+stroke, 3 invisible (OCR layers) |
| `repeats` | [int] | render modes of later passes that drew it again (Word's fake bold: `[1]`) |
| `line_width` | number or null | of the stroking pass, if any |
| `color` | int or null | sRGB as `0xRRGGBB` |
| `opacity` | number or null | 0–1 |
| `seqno` | int or null | drawing order on the page |
| `synthetic` | bool | a space PyMuPDF made up between glyphs, not drawn by the PDF |
| `actual_text` | bool | ActualText standing for several glyphs |
| `actual_text_glyph_ids` | [int] or null | the glyph ids that text stands for |
| `unattributed` | bool | the converter dropped it |
| `actual_text_ignored` | bool | drawn under an ActualText that was not used: its text is the glyph's own |

## Font

| field | type | meaning |
|---|---|---|
| `name` | string | as PyMuPDF names it |
| `converter` | string or null | |
| `rule` | int or string | as in Run |
| `matched` | string or null | what the rule matched: the repaired-as name, the converter name, `"sound map"` (repair checked the map and found it right), or the legacy family (`dv-tt`, `shree-lipi`, `akruti`, `krutidev`, `aps`, `chanakya`, `other`) |
| `repaired` | bool | its ToUnicode map was repaired in this document |
| `repaired_as` | string or null | |
| `programs` | [FontProgram] | the PDF font objects of this name |
| `bold`, `italic` | bool | decided by evidence every program carries |
| `bold_evidence`, `italic_evidence` | [string] | evidence only some programs carry ends in `(k of n programs)` and does not decide |

## FontProgram

| field | type | meaning |
|---|---|---|
| `xref` | int | the PDF object number |
| `pdf_name` | string | the PDF's font name, with subset prefix |
| `type` | string | `Type0`, `TrueType`, `Type1`, `Type3`, … |
| `encoding` | string | |
| `embedded` | bool | |
| `has_tounicode` | bool | before repair |
| `format` | string or null | `ttf`, `otf`, `cff`, … |
| `descriptor` | object | `FontWeight`, `ItalicAngle`, `Flags` where present |
| `names` | object | from the font's `name` table: `family`, `subfamily`, `full_name`, `version`, `postscript_name` |
| `weight` | int or null | OS/2 `usWeightClass` |
| `fs_selection` | int or null | OS/2 `fsSelection` |
| `mac_style` | int or null | head `macStyle` |
| `italic_angle` | number or null | post `italicAngle` |
| `error` | string or null | why metadata is missing |

## Issue

| field | type | meaning |
|---|---|---|
| `id` | string | `issue:000001`, … |
| `severity` | string | `info`, `warning`, `error` |
| `code` | string | see Issue codes |
| `message` | string | |
| `page` | int or null | |
| `font` | string or null | |
| `bbox` | box or null | |
| `context` | object | code-specific details |

## Evidence

Bold: `font_name_bold_keyword`, `pdf_descriptor_font_weight_N`,
`os2_us_weight_class_N`, `os2_fs_selection_bold`, `fill_then_stroke(W em)`,
`render_mode_1`, `render_mode_2`, `overprinted`. Glyph evidence on fewer than
half a run's ink glyphs is reported as `… (k of n glyphs)` and does not decide.

Italic: `font_name_italic_keyword`, `pdf_descriptor_italic_angle_A`,
`pdf_descriptor_flag_italic`, `os2_fs_selection_italic`,
`head_mac_style_italic`, `post_italic_angle_A`.

## Issue codes

| code | severity | when | context |
|---|---|---|---|
| `repair_failed` | warning | the repair raised; the document is read unrepaired | |
| `no_text_layer` | info | a page has no text (a scan) | |
| `legacy_font` | warning | words in a legacy 8-bit font were left out; Word's second font object (`…+1`) counts with its font | `family`, `words`, `regions`, `pages` |
| `no_converter` | warning | a font with no converter, and a name no legacy family knows, whose text looks like a legacy 8-bit encoding: its text is passed through | `characters`, `legacy`, `pages` |
| `unconverted_char` | warning | a converter had no rule for a character; it is missing from `text` | `glyph`, `char` |
| `converter_error` | warning | a converter raised on a run; the run's raw text stands | |
| `provenance_unavailable` | info | a converter with no per-glyph mapping: boxes are per run | |
| `unjoined_glyph` | info | PyMuPDF gave no glyph id for a glyph | `glyph` |
| `joined_words` | info | PyMuPDF split a word and unipdf joined it | `line`, `rule` |

## Changes

- **0.2** (unipdf 0.2.0): `Page.legacy_regions`, `Word.region`, rule and
  family `"legacy"`, issue `legacy_font`; `Glyph.actual_text_ignored`;
  `options.legacy`; issue `extraction_mismatch` is no longer raised;
  `--no-glyphs` output (unipdf 0.2.1); on a rotated page boxes and points
  are where the page is displayed (unipdf 0.2.1; 0.2.0 gave them in the
  unrotated page while `width` and `height` were the rotated ones).
- **0.1** (unipdf 0.1.0): first version.
