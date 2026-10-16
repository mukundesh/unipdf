"""Font records (UP-FN-1, UP-FN-6) and font-level bold/italic evidence
(UP-AT-2/3), ported from cidpdf (`_font_names_from_file`,
`_annotate_font_bold`, the italic rule of its word records).

Spans name their font but not its xref, and a page can carry several fonts of
one name. So a record is keyed by the name a span reports. It lists every
PDF font object (program) of that name on the pages read. Evidence that only
some of them carry is reported with a count and does not decide bold or
italic.

Records are snapshotted before ToUnicode repair, so `has_tounicode` describes
the PDF as it is.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

import pymupdf

logger = logging.getLogger(__name__)

SUBSET_RE = re.compile(r"^[A-Z]{6}\+")
REF_RE = re.compile(r"(\d+)\s+\d+\s+R")

BOLD_NAME_TOKENS = (
    "bold", "semibold", "semi bold", "demibold", "demi bold", "black", "heavy",
    "extrabold", "extra bold", "ultrabold", "ultra bold",
)
ITALIC_NAME_TOKENS = ("italic", "oblique")
NAME_IDS = {1: "family", 2: "subfamily", 4: "full_name", 5: "version", 6: "postscript_name"}


@dataclass
class FontProgram:
    """one PDF font object"""

    xref: int
    pdf_name: str
    type: str
    encoding: str
    embedded: bool
    has_tounicode: bool
    format: str | None = None  # ttf, otf, cff, ...
    descriptor: dict = field(default_factory=dict)  # FontWeight, ItalicAngle, Flags
    names: dict = field(default_factory=dict)  # family, subfamily, full_name, ...
    weight: int | None = None  # OS/2 usWeightClass
    fs_selection: int | None = None
    mac_style: int | None = None
    italic_angle: float | None = None  # post table
    error: str | None = None

    def bold_evidence(self, name: str) -> list[str]:
        ev = []
        text = " ".join(filter(None, [name, self.pdf_name, self.names.get("family"),
                                      self.names.get("subfamily"), self.names.get("full_name"),
                                      self.names.get("postscript_name")])).lower()
        if any(t in text for t in BOLD_NAME_TOKENS):
            ev.append("font_name_bold_keyword")
        w = self.descriptor.get("FontWeight")
        if isinstance(w, int | float) and w >= 600:
            ev.append(f"pdf_descriptor_font_weight_{int(w)}")
        if self.weight is not None and self.weight >= 600:
            ev.append(f"os2_us_weight_class_{self.weight}")
        if self.fs_selection is not None and self.fs_selection & 0x20:
            ev.append("os2_fs_selection_bold")
        return ev

    def italic_evidence(self, name: str) -> list[str]:
        ev = []
        text = " ".join(filter(None, [name, self.pdf_name, self.names.get("subfamily"),
                                      self.names.get("full_name"),
                                      self.names.get("postscript_name")])).lower()
        if any(t in text for t in ITALIC_NAME_TOKENS):
            ev.append("font_name_italic_keyword")
        a = self.descriptor.get("ItalicAngle")
        if isinstance(a, int | float) and abs(a) > 0.01:
            ev.append(f"pdf_descriptor_italic_angle_{a:g}")
        flags = self.descriptor.get("Flags")
        if isinstance(flags, int) and flags & 64:
            ev.append("pdf_descriptor_flag_italic")
        if self.fs_selection is not None and self.fs_selection & 0x01:
            ev.append("os2_fs_selection_italic")
        if self.mac_style is not None and self.mac_style & 0x02:
            ev.append("head_mac_style_italic")
        if self.italic_angle is not None and abs(self.italic_angle) > 0.01:
            ev.append(f"post_italic_angle_{self.italic_angle:g}")
        return ev


def _number(typ: str, val: str):
    if typ == "int":
        return int(val)
    if typ == "float":
        return float(val)
    return None


def _first_ref(doc: pymupdf.Document, typ: str, val: str) -> int | None:
    if typ == "xref":
        ref = int(REF_RE.match(val).group(1))
        obj = doc.xref_object(ref, compressed=True).strip()
        if not obj.startswith("["):
            return ref
        val = obj
    m = REF_RE.search(val)
    return int(m.group(1)) if m else None


def _descriptor(doc: pymupdf.Document, xref: int, ftype: str) -> dict:
    font = xref
    if ftype == "Type0":
        font = _first_ref(doc, *doc.xref_get_key(xref, "DescendantFonts"))
        if font is None:
            return {}
    typ, val = doc.xref_get_key(font, "FontDescriptor")
    if typ == "null":
        return {}
    desc = _first_ref(doc, typ, val) if typ == "xref" else None
    if desc is None:
        return {}
    out = {}
    for key in ("FontWeight", "ItalicAngle", "Flags"):
        v = _number(*doc.xref_get_key(desc, key))
        if v is not None:
            out[key] = v
    return out


def _program_metadata(prog: FontProgram, data: bytes) -> None:
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(data), lazy=True, fontNumber=0)
    if "name" in font:
        for rec in font["name"].names:
            attr = NAME_IDS.get(rec.nameID)
            if attr and attr not in prog.names:
                try:
                    prog.names[attr] = rec.toUnicode()
                except UnicodeDecodeError:
                    continue
    if "OS/2" in font:
        prog.weight = int(font["OS/2"].usWeightClass)
        prog.fs_selection = int(font["OS/2"].fsSelection)
    if "head" in font:
        prog.mac_style = int(font["head"].macStyle)
    if "post" in font:
        prog.italic_angle = float(font["post"].italicAngle)


def read_program(doc: pymupdf.Document, font: tuple) -> FontProgram:
    xref, ext, ftype, basefont, _, encoding = font[:6]
    prog = FontProgram(
        xref=xref, pdf_name=basefont, type=ftype, encoding=encoding,
        embedded=ext not in ("n/a", ""),
        has_tounicode=doc.xref_get_key(xref, "ToUnicode")[0] != "null",
        format=None if ext in ("n/a", "") else ext,
    )
    try:
        prog.descriptor = _descriptor(doc, xref, ftype)
        if prog.embedded and ext in ("ttf", "otf"):
            data = doc.extract_font(xref)[3]
            if data:
                _program_metadata(prog, data)
    except Exception as e:  # noqa: BLE001 - metadata is optional; say why it is missing
        prog.error = f"{type(e).__name__}: {e}"
        logger.info("font %s (xref %d): %s", basefont, xref, prog.error)
    return prog


def read_programs(doc: pymupdf.Document, pages) -> dict[str, list[FontProgram]]:
    """name a span reports (BaseFont without subset prefix) -> its programs"""
    seen: dict[int, FontProgram] = {}
    by_name: dict[str, list[FontProgram]] = {}
    for pno in pages:
        for font in doc[pno].get_fonts(full=True):
            if font[0] in seen or font[0] <= 0:
                continue
            prog = seen[font[0]] = read_program(doc, font)
            by_name.setdefault(SUBSET_RE.sub("", prog.pdf_name), []).append(prog)
    return by_name


def combine(per_program: list[list[str]]) -> tuple[bool, list[str]]:
    """evidence every program carries decides; the rest is reported with a count"""
    if not per_program:
        return False, []
    n = len(per_program)
    counts: dict[str, int] = {}
    for ev in per_program:
        for e in dict.fromkeys(ev):
            counts[e] = counts.get(e, 0) + 1
    decided = [e for e, k in counts.items() if k == n]
    partial = [f"{e} ({k} of {n} programs)" for e, k in counts.items() if k < n]
    return bool(decided), decided + partial


def name_evidence(name: str) -> tuple[list[str], list[str]]:
    """bold and italic evidence from the name alone (a font with no program)"""
    low = name.lower()
    bold = ["font_name_bold_keyword"] if any(t in low for t in BOLD_NAME_TOKENS) else []
    italic = ["font_name_italic_keyword"] if any(t in low for t in ITALIC_NAME_TOKENS) else []
    return bold, italic
