"""Which indic2unicode converter reads the text of a font (UP-FN-2..5).

One deterministic function from (font name, repair status) to a converter
name or None. The rules, in order:

1. The font was repaired in this document: the converter fix_tounicode names
   for the font it was repaired as (`get_font_converter`), or None. A repaired
   font's text is already Unicode, so if no converter is named nothing else
   applies.
2. A font whose converter reads its text both repaired and unrepaired
   (`dvotsurekh`, `sakal`: the entries of FONT_CONVERTERS that are not
   `*_glyphs` passes).
3. A FontConv key equal to the name, to the name without its subset prefix,
   or equal under `font_lookup_key` (case, separators and style suffix
   ignored). `*_glyphs` converters are never chosen here: they only read
   repaired text (UP-FN-3). There is no prefix matching: it maps `NudiUni01e`
   onto the 8-bit `nudi`.
   Except a font the repair knows how to fix (`get_glyph_fixes`) in a
   document where repair ran and left it alone: its map is sound and its text
   already right. FontConv's bare `Nirmala UI` / `Arial Unicode MS` keys name
   lossy converters for "a pdf that nothing has repaired", and applied to
   sound text they turn पश्चिम into प्चकम (a Word export with ActualText).
4. None: the text is passed through unchanged.

Before these, a legacy 8-bit font (convert/legacy.py) gets no converter and
the rule `"legacy"`: its words are left out (D-19). `legacy="keep"` turns
that off, for R's behaviour.

A caller can force a converter for every font or for named fonts (UP-FN-4);
that wins over everything, legacy fonts included.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from unipdf.convert.legacy import KEEP, SKIP, legacy_family
from unipdf.i2u.fix_tounicode import (
    FONT_CONVERTERS_BY_KEY,
    font_lookup_key,
    get_font_converter,
    get_glyph_fixes,
)

SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

RULE_REPAIRED = 1
RULE_READS_UNREPAIRED = 2
RULE_NAME = 3
RULE_NONE = 4
RULE_FORCED = "forced"
RULE_LEGACY = "legacy"

# Resolution.matched of a rule-4 font whose map the repair found sound
SOUND_MAP = "sound map"


def strip_subset(fontname: str) -> str:
    """'ABCDEE+Sakal Marathi' -> 'Sakal Marathi'"""
    return SUBSET_PREFIX_RE.sub("", fontname or "")


def is_glyphs_converter(name: str) -> bool:
    return name.endswith("_glyphs")


@dataclass(frozen=True)
class Resolution:
    converter: str | None
    rule: int | str
    # what the rule matched on: the repaired-as name, the FontConv key, the
    # forced name
    matched: str | None = None


class ConverterResolver:
    def __init__(
        self,
        converter_names: Iterable[str],
        force: str | None = None,
        font_map: Mapping[str, str] | None = None,
        legacy: str = SKIP,
    ):
        if legacy not in (SKIP, KEEP):
            raise ValueError(f"legacy must be {SKIP!r} or {KEEP!r}")
        self.skip_legacy = legacy == SKIP
        names = set(converter_names)
        for forced in [force, *(font_map or {}).values()]:
            if forced is not None and forced not in names:
                raise ValueError(f"unknown converter: {forced!r}")
        self.names = names
        self.force = force
        # --font-map is matched like rule 3: exact, then by lookup key
        self.font_map = dict(font_map or {})
        self.font_map_by_key = {font_lookup_key(k): v for k, v in self.font_map.items()}
        # rule 3 candidates. Several keys can share a lookup key ('Nirmala UI'
        # and 'nirmalaui'); the first in sorted order is the one reported
        self.by_key: dict[str, str] = {}
        for name in sorted(names):
            if not is_glyphs_converter(name):
                self.by_key.setdefault(font_lookup_key(name), name)

    def resolve(self, fontname: str, repaired: Mapping[str, str] | None) -> Resolution:
        """fontname: the font name a PyMuPDF span reports.
        repaired: ToUnicodeFixer.fixed_font_names of this document (the name
        the pdf carries, without subset prefix -> the name it was repaired as),
        or None when repair was not run."""
        name = strip_subset(fontname)

        if name in self.font_map:
            return Resolution(self.font_map[name], RULE_FORCED, name)
        key = font_lookup_key(name)
        if key in self.font_map_by_key:
            return Resolution(self.font_map_by_key[key], RULE_FORCED, name)
        if self.force is not None:
            return Resolution(self.force, RULE_FORCED, None)
        if self.skip_legacy:
            family = legacy_family(name)
            if family is not None:
                return Resolution(None, RULE_LEGACY, family)

        # 1. repaired in this document, matched by exact name only: a bold
        # that was not repaired must not inherit its regular's repair
        if repaired is not None and name in repaired:
            repaired_as = repaired[name]
            return Resolution(get_font_converter(repaired_as), RULE_REPAIRED, repaired_as)

        # 2. converters that read repaired and unrepaired text alike
        conv = FONT_CONVERTERS_BY_KEY.get(key)
        if conv is not None and not is_glyphs_converter(conv):
            return Resolution(conv, RULE_READS_UNREPAIRED, name)

        # 3. the FontConv registry by name, unless the repair vouched for the map
        if repaired is not None and get_glyph_fixes(name) is not None:
            return Resolution(None, RULE_NONE, SOUND_MAP)
        for candidate in (fontname, name):
            if candidate in self.names and not is_glyphs_converter(candidate):
                return Resolution(candidate, RULE_NAME, candidate)
        if key in self.by_key:
            return Resolution(self.by_key[key], RULE_NAME, self.by_key[key])

        return Resolution(None, RULE_NONE, None)
