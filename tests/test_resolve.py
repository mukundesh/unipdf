"""Converter resolution (UP-FN-2..5), including the two read_pdf.py bugs."""

import pytest

from unipdf.convert.resolve import (
    RULE_FORCED,
    RULE_LEGACY,
    RULE_NAME,
    RULE_NONE,
    RULE_READS_UNREPAIRED,
    RULE_REPAIRED,
    SOUND_MAP,
    ConverterResolver,
    strip_subset,
)
from unipdf.i2u.fontconv import FontConv


@pytest.fixture(scope="module")
def resolver():
    return ConverterResolver(FontConv().converters)


@pytest.fixture(scope="module")
def keep_resolver():
    return ConverterResolver(FontConv().converters, legacy="keep")


def r(resolver, name, repaired=None):
    res = resolver.resolve(name, repaired or {})
    return res.converter, res.rule


def test_strip_subset():
    assert strip_subset("ABCDEE+Sakal Marathi") == "Sakal Marathi"
    assert strip_subset("CIDFont+F1") == "CIDFont+F1"
    assert strip_subset("") == ""


# read_pdf.py bug 1: *_glyphs applied to a font that was not repaired
@pytest.mark.parametrize("name", ["Mangal", "Mangal,Bold", "Mangal-Bold", "ABCDEE+Mangal"])
def test_unrepaired_mangal_gets_no_converter(resolver, name):
    assert r(resolver, name) == (None, RULE_NONE)


@pytest.mark.parametrize("name", ["Arial Unicode MS", "Nirmala UI", "NirmalaUI", "NirmalaUI-Bold"])
def test_sound_map_gets_no_converter(resolver, name):
    # repair ran, knows the font, changed nothing: the text is already right
    res = resolver.resolve(name, {})
    assert (res.converter, res.rule, res.matched) == (None, RULE_NONE, SOUND_MAP)


@pytest.mark.parametrize("name,conv", [("Arial Unicode MS", "Arial Unicode MS"),
                                       ("NirmalaUI-Bold", "Nirmala UI")])
def test_without_repair_the_lossy_converters_apply(resolver, name, conv):
    # never a *_glyphs pass, but the converters written for unrepaired pdfs
    res = resolver.resolve(name, None)
    assert (res.converter, res.rule) == (conv, RULE_NAME)


def test_without_repair_mangal_still_gets_nothing(resolver):
    assert resolver.resolve("Mangal", None).converter is None


# read_pdf.py bug 2: prefix matching mapped NudiUni01e onto the 8-bit nudi
def test_unrepaired_nudiuni_is_not_nudi(resolver):
    assert r(resolver, "NudiUni01e") == (None, RULE_NONE)


def test_repaired_fonts_get_their_glyphs_pass(resolver):
    assert r(resolver, "Nirmala UI", {"Nirmala UI": "Nirmala UI"}) == ("nirmalaui_glyphs", RULE_REPAIRED)
    assert r(resolver, "NirmalaUI-Bold", {"NirmalaUI-Bold": "NirmalaUI-Bold"}) == ("nirmalaui_glyphs", RULE_REPAIRED)
    assert r(resolver, "ABCDEE+Mangal", {"Mangal": "Mangal"}) == ("mangal_glyphs", RULE_REPAIRED)
    assert r(resolver, "Arial Unicode MS", {"Arial Unicode MS": "Arial Unicode MS"}) == ("arialuni_glyphs", RULE_REPAIRED)
    assert r(resolver, "NudiUni01e", {"NudiUni01e": "NudiUni01e"}) == ("nudiuni_glyphs", RULE_REPAIRED)


def test_repaired_under_a_recovered_name(resolver):
    # a producer that names every font CIDFont+Fn: repaired as the program's name
    assert r(resolver, "CIDFont+F1", {"CIDFont+F1": "Mangal"}) == ("mangal_glyphs", RULE_REPAIRED)


def test_repair_is_matched_by_exact_name_only(resolver):
    # the regular was repaired, the bold was not: the bold is not repaired text
    assert r(resolver, "Mangal,Bold", {"Mangal": "Mangal"}) == (None, RULE_NONE)


def test_repaired_font_with_no_reordering_pass(resolver):
    assert r(resolver, "SomeFont", {"SomeFont": "SomeFont"}) == (None, RULE_REPAIRED)


@pytest.mark.parametrize("name", ["DVOT-SurekhMR", "DVOT-SurekhMR,Bold", "DVOTSurekhMRBold",
                                  "DVOTSurekhMRNormal", "ABCDEE+DVOT-SurekhMR", "DVOT-YogeshMR"])
def test_dvot_reads_repaired_and_unrepaired(resolver, name):
    assert r(resolver, name) == ("dvotsurekh", RULE_READS_UNREPAIRED)
    assert r(resolver, name, {strip_subset(name): strip_subset(name)})[0] == "dvotsurekh"


@pytest.mark.parametrize("name", ["Sakal Marathi", "SakalMarathi", "SakalMarathi-Normal", "ABCDEE+Sakal Marathi"])
def test_sakal_reads_repaired_and_unrepaired(resolver, name):
    assert r(resolver, name) == ("sakal", RULE_READS_UNREPAIRED)


@pytest.mark.parametrize("name,conv", [("TM-Chanakya-Normal", "TM-Chanakya-Normal"),
                                       ("FourCMRAbhishek", "FourCMRAbhishek"),
                                       ("DVBWTTYogeshBold", "DVBWTTYogeshBold")])
def test_legacy_fonts_by_name_when_kept(keep_resolver, name, conv):
    # legacy="keep": R's resolution
    assert r(keep_resolver, name) == (conv, RULE_NAME)


@pytest.mark.parametrize("name", ["DVB-TTSurekh", "DVB-TTSurekhEN", "DVB-TTYogesh", "DVB-TTYogesh,Bold"])
def test_dvb_tt_kept_is_unconverted(keep_resolver, name):
    assert r(keep_resolver, name) == (None, RULE_NONE)


@pytest.mark.parametrize("name,family", [
    ("DVB-TTSurekh", "dv-tt"), ("ABCDEE+DVB-TTYogesh+1", "dv-tt"), ("DVBWTTYogeshBold", "dv-tt"),
    ("DVTTSurekhNormal", "dv-tt"), ("DV-TTSurekh_Normal0137.5", "dv-tt"),
    ("MG Shree", "shree-lipi"), ("SHREE-DEV7-0714", "shree-lipi"),
    ("AkrutiDevPriya,Bold", "akruti"), ("Kruti Dev 010", "krutidev"),
    ("TM-Chanakya-Normal", "chanakya")])
def test_legacy_fonts_are_skipped(resolver, name, family):
    # D-19, including fonts a converter reads by name (DVBW-TTYogesh, Chanakya)
    res = resolver.resolve(name, {})
    assert (res.converter, res.rule, res.matched) == (None, RULE_LEGACY, family)


@pytest.mark.parametrize("name", ["DVOT-SurekhMR", "DVOTSurekhMRBold", "AkrutiDevPriyaUnicode",
                                  "FourCMRAbhishek", "KrishnaUni", "Sakal Marathi", "Mangal"])
def test_unicode_fonts_are_not_legacy(resolver, name):
    assert resolver.resolve(name, {}).rule != RULE_LEGACY


def test_forced_wins_over_legacy():
    res = ConverterResolver(FontConv().converters, font_map={"DVB-TTYogesh": "yogesh"})
    assert r(res, "DVB-TTYogesh") == ("yogesh", RULE_FORCED)
    assert r(res, "DVB-TTSurekh") == (None, RULE_LEGACY)


@pytest.mark.parametrize("name", ["Arial", "Times New Roman", "Calibri,Bold", "TimesNewRomanPSMT", "Wingdings"])
def test_latin_fonts_get_nothing(resolver, name):
    assert r(resolver, name) == (None, RULE_NONE)


def test_glyphs_converter_names_are_never_matched_by_name(resolver):
    assert r(resolver, "mangal_glyphs") == (None, RULE_NONE)


def test_forced_for_every_font():
    res = ConverterResolver(FontConv().converters, force="chanakya")
    assert res.resolve("Arial", {}).converter == "chanakya"
    assert res.resolve("Arial", {}).rule == RULE_FORCED


def test_font_map_applies_to_named_fonts_only():
    res = ConverterResolver(FontConv().converters, font_map={"DVB-TTSurekh": "surekh"})
    assert (res.resolve("ABCDEE+DVB-TTSurekh", {}).converter, res.resolve("DVB-TTSurekh", {}).rule) == ("surekh", RULE_FORCED)
    assert res.resolve("DVB-TTSurekh,Bold", {}).converter == "surekh"  # by lookup key
    assert res.resolve("Sakal Marathi", {}).converter == "sakal"


def test_unknown_forced_converter_is_an_error():
    with pytest.raises(ValueError):
        ConverterResolver(FontConv().converters, force="nosuchfont")
