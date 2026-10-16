"""Tracked conversion (UP-AL-1/2), ported from `spikes/m0/tracked.py`.

BaseFont's passes are run as functions over `(token, sources)` pairs, where
`sources` are indices into the string given to `to_unicode`. Every comparison
is made on the token, so the passes decide exactly as BaseFont's do and the
text comes out the same (UP-AL-3; pinned by test_provenance_equivalence.py).
The absorbed converters are not edited (D-16): these functions read their
lexers and tables.

Converters that change the string before BaseFont's passes have pre-pass
adapters. An adapter stands only for the `to_unicode` it was written for; any
other override falls back to run-level provenance (all output from all input),
never to wrong provenance.
"""

from __future__ import annotations

from collections.abc import Callable

from unipdf.i2u.fonts.basefont import LITERAL, BaseFont
from unipdf.i2u.fonts.glyphs.arialuni_glyphs import ArialUniGlyphs
from unipdf.i2u.fonts.hindi.chanakya import Chanakya
from unipdf.i2u.fonts.marathi.abhishek import Abhishek
from unipdf.i2u.fonts.marathi.sakal import Sakal

Sources = tuple[int, ...]
Pieces = list[tuple[str, Sources]]


def _union(pairs) -> Sources:
    s: set[int] = set()
    for _, src in pairs:
        s.update(src)
    return tuple(sorted(s))


def tokenize(font: BaseFont, data: str):
    out = []
    font.lexer.input(data)
    while True:
        tok = font.lexer.token()
        if not tok:
            break
        # lexpos .. lexpos after the token: right for LITERAL tokens too
        src = tuple(range(tok.lexpos, font.lexer.lexpos))
        if tok.type == LITERAL:
            out.append(((LITERAL, tok.value), src))
            continue
        multiple = font.multiple_tokens(tok.type)
        if multiple:
            out.extend((t, src) for t in multiple)
        else:
            out.append((tok.type, src))
    return out


def _match(composelist, pairs, i) -> bool:
    if len(composelist) > len(pairs) - i:
        return False
    return all(x == pairs[i + k][0] for k, x in enumerate(composelist))


def compose_tokens(font: BaseFont, pairs, compose_rules=None):
    if compose_rules is None:
        compose_rules = font.composeTokens
    for compose in list(compose_rules.keys()):
        out, repl, i = [], compose_rules[compose], 0
        while i < len(pairs):
            if _match(compose, pairs, i):
                src = _union(pairs[i:i + len(compose)])
                if type(repl) is list:
                    out.extend((r, src) for r in repl)
                else:
                    out.append((repl, src))
                i += len(compose)
            else:
                out.append(pairs[i])
                i += 1
        pairs = out
    return pairs


def jump_before_tokens(font: BaseFont, pairs):
    out = []
    for p in pairs:
        num, index = font.num_before(p[0]), len(out)
        while num > 0 and index > 0:
            index -= 1
            if out[index][0] not in font.jumpover and \
                    not font.is_invisible_literal(out[index][0]):
                num -= 1
        if num > 0:
            out.append(p)
        else:
            out.insert(index, p)
    return out


def jump_after_tokens(font: BaseFont, pairs):
    out, waiting = [], []
    for p in pairs:
        t = p[0]
        num = font.num_after(t)
        if num != 0:
            waiting.append([p, num])
        elif t in font.waitover or font.is_invisible_literal(t):
            out.append(p)
        else:
            pending, waiting = waiting, []
            for w in pending:
                if w[1] == 0:
                    out.append(w[0])
                elif t in font.halftokens:
                    waiting.append(w)
                else:
                    w[1] -= 1
                    waiting.append(w)
            out.append(p)
    out.extend(w[0] for w in waiting)
    return out


def tokens_to_unicode(font: BaseFont, pairs) -> Pieces:
    pieces = []
    for t, src in pairs:
        ustr = font.token_to_unicode(t)
        if ustr is not None:
            pieces.append((ustr, src))
    return pieces


def base_to_unicode(font: BaseFont, data: str) -> Pieces:
    pairs = tokenize(font, data)
    pairs = compose_tokens(font, pairs)
    pairs = jump_before_tokens(font, pairs)
    pairs = jump_after_tokens(font, pairs)
    return tokens_to_unicode(font, pairs)


def _remap(pieces: Pieces, index_map: list[int]) -> Pieces:
    """sources indexing a pre-processed string -> indices of the original,
    index_map[i] being the original index of new character i"""
    return [(s, tuple(sorted({index_map[i] for i in src}))) for s, src in pieces]


# ---- pre-pass adapters (UP-AL-2): a font's to_unicode replayed with an index map


def _chanakya(font: Chanakya, data: str) -> Pieces:
    keep = [i for i, c in enumerate(data) if c not in "‌‍"]
    return _remap(base_to_unicode(font, "".join(data[i] for i in keep)), keep)


def _sakal(font: Sakal, data: str) -> Pieces:
    new = font.glyph_codes(data)  # 1:1 per character; keeps the numbering state
    if len(new) != len(data):
        raise AssertionError("sakal glyph_codes is no longer 1:1")
    return base_to_unicode(font, new)


def _arialuni_glyphs(font: ArialUniGlyphs, data: str) -> Pieces:
    out, start = [], 0
    for script, segment in font.split_scripts(data):
        if script is None:
            pieces = base_to_unicode(font, segment)
        else:
            pieces = tracked_to_unicode(font.scriptobjs[script], segment)
        out.extend((s, tuple(i + start for i in src)) for s, src in pieces)
        start += len(segment)
    if start != len(data):
        raise AssertionError("arialuni_glyphs split_scripts no longer covers its input")
    return out


def _abhishek(font: Abhishek, data: str) -> Pieces:
    """its own pipeline: drop SPACER tokens, then the second copy of a token
    two glyphs share. The copy's glyph is part of the character it repeats,
    so its sources join the kept token's"""
    pairs = [p for p in tokenize(font, data) if p[0] != "SPACER"]
    tokens = [t for t, _ in pairs]
    out: list = []
    out_src: list[set[int]] = []
    for i, (t, src) in enumerate(pairs):
        if out and out[-1] == t and font.is_second_copy(out, tokens, i):
            out_src[-1].update(src)
            continue
        out.append(t)
        out_src.append(set(src))
    return tokens_to_unicode(font, [(t, tuple(sorted(s))) for t, s in zip(out, out_src,
                                                                          strict=True)])


ADAPTERS: list[tuple[type, Callable[..., Pieces]]] = [
    (Sakal, _sakal),
    (Chanakya, _chanakya),
    (ArialUniGlyphs, _arialuni_glyphs),
    (Abhishek, _abhishek),
]


def provenance_level(font: BaseFont) -> str:
    """'piece' where output pieces have their own sources, else 'run'"""
    for cls, _ in ADAPTERS:
        if isinstance(font, cls) and type(font).to_unicode is cls.to_unicode:
            return "piece"
    return "piece" if type(font).to_unicode is BaseFont.to_unicode else "run"


def tracked_to_unicode(font: BaseFont, data: str) -> Pieces:
    """[(text, sources)] whose texts join to font.to_unicode(data)"""
    for cls, fn in ADAPTERS:
        if isinstance(font, cls) and type(font).to_unicode is cls.to_unicode:
            return fn(font, data)
    if type(font).to_unicode is BaseFont.to_unicode:
        return base_to_unicode(font, data)
    # an override with no adapter: run-level provenance
    text = font.to_unicode(data)
    return [(text, tuple(range(len(data))))] if text else []
