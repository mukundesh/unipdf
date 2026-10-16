"""indic2unicode's string API for text that is not in a PDF (UP-API-2).

    unipdf.convert("chanakya", text)
    unipdf.convert_with_provenance("chanakya", text)  # [(piece, [input indices])]

`converter` is a converter name (`unipdf.converter_names()`), as for
indic2unicode's `FontConv.to_unicode`. One FontConv serves every call, so a
stateful converter (sakal's numbering) carries its state from one call to the
next, as it does in indic2unicode.
"""

from __future__ import annotations

import functools

from unipdf.convert.provenance import tracked_to_unicode
from unipdf.i2u.fontconv import FontConv


@functools.cache
def _fontconv() -> FontConv:
    return FontConv()


def _converter(name: str):
    try:
        return _fontconv().converters[name]
    except KeyError:
        raise ValueError(f"unknown converter: {name!r}") from None


def converter_names() -> list[str]:
    return sorted(_fontconv().converters)


def convert(converter: str, text: str) -> str:
    """text in `converter`'s encoding -> Unicode, exactly as indic2unicode"""
    return _converter(converter).to_unicode(text)


def convert_with_provenance(converter: str, text: str) -> list[tuple[str, list[int]]]:
    """the same text in pieces, each with the indices of `text` it came from.
    The pieces join to `convert(converter, text)`. A converter with no index
    map gives one piece from all of `text`."""
    return [(piece, list(src)) for piece, src in tracked_to_unicode(_converter(converter), text)]
