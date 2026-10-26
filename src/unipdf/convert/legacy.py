"""Legacy 8-bit Devanagari fonts, which unipdf leaves out (D-19).

An 8-bit font puts its glyphs on the bytes of a Latin code page, so its text
in a PDF is Latin to an extractor, and Word's export loses some of its
characters (OQ-8). unipdf does not read these fonts: their words keep their
boxes and raw text, but no text, and are gathered into regions another tool
can read (`Page.legacy_regions`).

A font is legacy by its name: the family patterns below, from the fonts of
the mahfin2 corpus (tools/legacy_font_docs.py). The Unicode DVOT fonts
(DVOT-SurekhMR, …), AkrutiDevPriyaUnicode and FourCMRAbhishek (OpenType with
a broken map) are not legacy.
"""

from __future__ import annotations

import re

SKIP, KEEP = "skip", "keep"

# family -> pattern on the name without its subset prefix
LEGACY_FAMILIES = {
    # C-DAC / Modular ISM: DV-TT, DVB-TT, DVBW-TT, DVI-TT, DVW-TT, DVTT, DVBTT…
    # but not DVOT-, the OpenType Unicode fonts
    "dv-tt": r"^DV[A-Z]{0,3}-?TT",
    "shree-lipi": r"^MG ?Shree|^SHREE-DEV",
    "akruti": r"^Akruti(Dev|Office)(?!.*Unicode)",
    "krutidev": r"^Kruti ?Dev",
    "aps": r"^APS-.*DV",
    "chanakya": r"Chanakya",
    "other": r"^(Arjun|Shivaji|Devlys|Krishna(Bold)?$|Priyaanka|Aryan2|Divya)",
}
_LEGACY_RE = {family: re.compile(p, re.IGNORECASE) for family, p in LEGACY_FAMILIES.items()}

# the placeholder `text` puts where a region's words were; N is the region
# number on its page, from 1 as in `unipdf regions`
PLACEHOLDER = "⟦8bit:{}⟧"


def legacy_family(name: str) -> str | None:
    """the legacy family of a font name without its subset prefix, or None"""
    for family, pattern in _LEGACY_RE.items():
        if pattern.search(name):
            return family
    return None
