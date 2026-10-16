# S2 prototype: BaseFont's passes run over (token, sources) pairs.
# sources is a tuple of indices into the string handed to to_unicode().
# Every comparison is made on pair[0], so the passes take the same decisions
# as BaseFont's and the text must come out identical.
from indic2unicode.fonts.basefont import BaseFont, LITERAL
from indic2unicode.fonts.hindi.chanakya import Chanakya
from indic2unicode.fonts.marathi.sakal import Sakal
from indic2unicode.fonts.glyphs.arialuni_glyphs import ArialUniGlyphs


def union(pairs):
    s = set()
    for _, src in pairs:
        s.update(src)
    return tuple(sorted(s))


def tokenize(font, data):
    out = []
    font.lexer.input(data)
    while True:
        tok = font.lexer.token()
        if not tok:
            break
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


def match(composelist, tlist, i):
    if len(composelist) > len(tlist) - i:
        return False
    return all(x == tlist[i + k][0] for k, x in enumerate(composelist))


def compose_tokens(font, out1, composeTokens=None):
    if composeTokens is None:
        composeTokens = font.composeTokens
    for compose in list(composeTokens.keys()):
        out2, repl, i = [], composeTokens[compose], 0
        while i < len(out1):
            if match(compose, out1, i):
                src = union(out1[i:i + len(compose)])
                if type(repl) == list:
                    out2.extend((r, src) for r in repl)
                else:
                    out2.append((repl, src))
                i += len(compose)
            else:
                out2.append(out1[i])
                i += 1
        out1 = out2
    return out1


def jump_before_tokens(font, pairs):
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


def jump_after_tokens(font, pairs):
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


def tokens_to_unicode(font, pairs):
    pieces, dropped = [], []
    for t, src in pairs:
        ustr = font.token_to_unicode(t)
        if ustr is not None:
            pieces.append((ustr, src))
        else:
            dropped.append((t, src))
    return pieces, dropped


def base_to_unicode(font, data):
    pairs = tokenize(font, data)
    pairs = compose_tokens(font, pairs)
    pairs = jump_before_tokens(font, pairs)
    pairs = jump_after_tokens(font, pairs)
    pieces, _ = tokens_to_unicode(font, pairs)
    return pieces


def remap(pieces, index_map):
    """pieces whose sources index a pre-processed string -> indices of the
       original string, index_map[i] being the original index of new char i"""
    return [(s, tuple(sorted({index_map[i] for i in src}))) for s, src in pieces]


# ---- pre-pass adapters: the to_unicode() of a font that alters the string
# before BaseFont's passes, replayed with an index map

def chanakya_to_unicode(font, data):
    keep = [i for i, c in enumerate(data) if c not in '‌‍']
    new = ''.join(data[i] for i in keep)
    assert new == data.replace('‌', '').replace('‍', '')
    return remap(base_to_unicode(font, new), keep)


def sakal_to_unicode(font, data):
    new = font.glyph_codes(data)          # 1:1 per character, keeps state
    assert len(new) == len(data)
    return base_to_unicode(font, new)


def arialuni_glyphs_to_unicode(font, data):
    out, start = [], 0
    for script, segment in font.split_scripts(data):
        if script is None:
            pieces = base_to_unicode(font, segment)
        else:
            pieces = tracked_to_unicode(font.scriptobjs[script], segment)
        out.extend((s, tuple(i + start for i in src)) for s, src in pieces)
        start += len(segment)
    assert start == len(data)
    return out


ADAPTERS = [(Sakal, sakal_to_unicode), (Chanakya, chanakya_to_unicode),
            (ArialUniGlyphs, arialuni_glyphs_to_unicode)]


def tracked_to_unicode(font, data):
    """[(text, sources)] whose texts join to font.to_unicode(data)"""
    for cls, fn in ADAPTERS:
        # the adapter only stands for the to_unicode() it was written for
        if isinstance(font, cls) and type(font).to_unicode is cls.to_unicode:
            return fn(font, data)
    if type(font).to_unicode is BaseFont.to_unicode:
        return base_to_unicode(font, data)
    # an override with no adapter: run level provenance
    text = font.to_unicode(data)
    return [(text, tuple(range(len(data))))] if text else []
