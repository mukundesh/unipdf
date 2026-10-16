# unipdf JSON, schema 0.1

What `unipdf json` and `Document.to_json()` give (UP-MD-1, UP-MD-2). The
field tables below are checked against the output by `tests/test_json.py`:
every field listed is emitted and every field emitted is listed.

Conventions:

- Coordinates are PDF points, **top-left origin** (PyMuPDF's); boxes are
  `[x0, y0, x1, y1]`, points `[x, y]`. Numbers are rounded to 3 decimals.
- Indices are **0-based** and **per page**: a word's `glyphs` index
  `page.glyphs`, a line's `words` index `page.words`. (The `words` and
  `glyphs` commands' tables number from 1.)
- Fonts are named by the name PyMuPDF spans report (BaseFont without the
  subset prefix); `fonts[].name` is the key.
- Output is deterministic: no timestamps, stable order. `source.filename` is
  the path as given.
- Text: `text` is Unicode in logical order where a converter made it or the
  repair vouched for the map; `raw_text`/`raw` is what the PDF gives after
  ToUnicode repair, before conversion (D-13).

## Document

| field | type | meaning |
|---|---|---|
| `schema_version` | string | `"0.1"` |
| `source` | object | `filename` (null when read from bytes), `sha256`, `size` (bytes) |
| `options` | object | the `unipdf.open()` arguments in effect: `pages` (null = all), `repair`, `force`, `font_map`, `join`, `rawdict_lines`, `j2`, `actual_text` (`"bypass"`/`"convert"`), `row_tolerance` |
| `pages` | [Page] | the pages read, in order |
| `fonts` | [Font] | one per font name met on those pages |
| `issues` | [Issue] | what could not be done, in the order met |
| `repaired` | object or null | font name → name the ToUnicode repair treated it as; null when repair did not run or failed |

## Page

| field | type | meaning |
|---|---|---|
| `index` | int | 0-based page number in the PDF |
| `width`, `height` | number | page size in points (after rotation, as PyMuPDF's `page.rect`) |
| `rotation` | int | `/Rotate` |
| `blocks` | [int] | `rawdict` block numbers holding text, in output order |
| `lines` | [Line] | output lines: visual rows (default) or `rawdict` lines (`rawdict_lines`) |
| `words` | [Word] | in reading order |
| `runs` | [Run] | conversion units |
| `glyphs` | [Glyph] | every glyph record of the page, in `rawdict` order |

## Line

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `block` | int | the `rawdict` block it belongs to |
| `bbox` | box or null | union of its glyphs |
| `text` | string | as `unipdf text` prints it |
| `words` | [int] | its words |
| `sources` | [[int, int]] | `(block, line)` of the `rawdict` lines merged into it |

## Word

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `line` | int | its line |
| `text` | string | converted text |
| `raw_text` | string | text of its glyphs before conversion (D-13) |
| `bbox` | box or null | union of the boxes of its glyphs, spaces left out |
| `glyphs` | [int] | the glyphs its text came from, and its `unattributed` glyphs, in `rawdict` order |
| `glyph_ids` | [int] | font glyph ids of those glyphs (D-13); an ActualText group gives the ids of the glyphs it replaces, so the list can be longer than `glyphs` |
| `fonts` | [string] | fonts of its glyphs, in order of first use |
| `size` | number or null | most common glyph size |
| `sizes` | [number] | all glyph sizes, ascending |
| `bbox_level` | string | `"word"` |
| `joined_from` | [string] or null | the parts the extraction split it into, when unipdf joined them (UP-LY-5) |
| `join_rules` | [string] or null | rule of each removed space: `"J1"` (mark starts the next part), `"J2"` (narrow generated space) |
| `unattributed` | [int] | glyphs the converter dropped, given to the nearest word (UP-AL-7): in `glyphs`, `raw_text` and `bbox`, not in `text` |
| `clusters` | [Cluster] or null | aksharas with boxes; null when a run of it has only run-level provenance |
| `font_runs` | [FontRun] | the parts of the word in one font (UP-AT-4) |
| `bold`, `italic` | bool | bold if any font run is; italic likewise |
| `bold_evidence`, `italic_evidence` | [string] | the evidence of the runs that decided (see Evidence) |

## Cluster

| field | type | meaning |
|---|---|---|
| `text` | string | one akshara |
| `bbox` | box or null | union of its glyphs |
| `glyphs` | [int] | the glyphs it came from |

## FontRun

| field | type | meaning |
|---|---|---|
| `font` | string | |
| `text`, `raw_text` | string | |
| `bbox` | box or null | |
| `glyphs` | [int] | |
| `size` | number or null | most common glyph size |
| `bold`, `italic` | bool | |
| `bold_evidence`, `italic_evidence` | [string] | |

## Run

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `block`, `line` | int | its `rawdict` line |
| `font` | string | |
| `converter` | string or null | indic2unicode converter used; null = text passed through |
| `rule` | int or `"forced"` | resolution rule (UP-FN-2): 1 repaired, 2 reads unrepaired, 3 by name, 4 none |
| `raw` | string | the glyphs' text before conversion |
| `text` | string | converted text |
| `glyphs` | [int] | |
| `pieces` | [[string, [int]]] | provenance: each piece of `text` with the glyphs it came from |
| `actual_text` | bool | holds ActualText glyphs (D-18) |
| `provenance` | string | `"piece"`, or `"run"` when every piece comes from the whole run |
| `logical` | bool | `text` is known to be in logical order |
| `error` | string or null | the converter's exception; `text` is then `raw` (UP-CV-5) |

## Glyph

| field | type | meaning |
|---|---|---|
| `index` | int | |
| `text` | string | what `rawdict` gives for it after repair (may be several code points) |
| `glyph_id` | int or null | font glyph id from `texttrace`; null for ActualText groups and unjoined glyphs |
| `origin` | point | pen position |
| `bbox` | box | `rawdict`'s box (D-14) |
| `font` | string | |
| `size` | number | |
| `block`, `line` | int | its `rawdict` line |
| `render_mode` | int or null | 0 fill, 1 stroke, 2 fill+stroke, 3 invisible (OCR layers) |
| `repeats` | [int] | render modes of later passes that drew it again (Word's fake bold: `[1]`) |
| `line_width` | number or null | of the stroking pass, if any |
| `color` | int or null | sRGB as `0xRRGGBB` |
| `opacity` | number or null | 0–1 |
| `seqno` | int or null | drawing order on the page |
| `synthetic` | bool | a space MuPDF generated (UP-EX-5) |
| `actual_text` | bool | `/ActualText` replacement text standing for several glyphs (UP-EX-7) |
| `actual_text_glyph_ids` | [int] or null | the glyph ids that text replaces |
| `unattributed` | bool | the converter dropped it |

## Font

| field | type | meaning |
|---|---|---|
| `name` | string | as spans report it |
| `converter` | string or null | |
| `rule` | int or `"forced"` | as in Run |
| `matched` | string or null | what the rule matched: repaired-as name, converter name, `"sound map"` |
| `repaired` | bool | its ToUnicode map was repaired in this document |
| `repaired_as` | string or null | |
| `programs` | [FontProgram] | the PDF font objects of this name |
| `bold`, `italic` | bool | decided by evidence every program carries |
| `bold_evidence`, `italic_evidence` | [string] | evidence only some programs carry ends in `(k of n programs)` and does not decide |

## FontProgram

| field | type | meaning |
|---|---|---|
| `xref` | int | |
| `pdf_name` | string | BaseFont, with subset prefix |
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
| `repair_failed` | warning | ToUnicode repair raised; the document is read unrepaired | |
| `no_text_layer` | info | a page has no text | |
| `no_converter` | warning | a font with no converter whose text looks like a legacy 8-bit encoding | `characters`, `legacy`, `suggest`, `pages` |
| `unconverted_char` | warning | a converter had no token for a character; it is missing from `text` | `glyph`, `char` |
| `converter_error` | warning | a converter raised on a run; the run's raw text stands | |
| `provenance_unavailable` | info | a converter with no index map: boxes are per run | |
| `unjoined_glyph` | info | a glyph could not be joined to `texttrace` (no glyph id) | `glyph` |
| `joined_words` | info | the extraction split a word and unipdf joined it | `line`, `rule` |
| `extraction_mismatch` | warning | the two `rawdict` extractions disagree on lines; ActualText is not detected on the page | |
