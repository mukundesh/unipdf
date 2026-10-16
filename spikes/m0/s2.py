# S2: tracked conversion == to_unicode, and every output char has a source
import sys, os, re, collections, pymupdf
sys.path.insert(0, '/Users/mukund/orgpedia/Try/indic2unicode')
import logging; logging.disable(logging.CRITICAL)
from indic2unicode.fontconv import FontConv
from indic2unicode.tools.fix_tounicode import ToUnicodeFixer, get_font_converter
import tracked
I2U = '/Users/mukund/orgpedia/Try/indic2unicode/indic2unicode'
DEVA = ['abhishek', 'arialuni', 'arialuni_glyphs', 'aryan2', 'chanakya', 'dvotsurekh', 'mangal_glyphs',
        'nirmalaui', 'nirmalaui_glyphs', 'sakal', 'surekh', 'yogesh']

def check(name, runs, st, ex):
    a, b = FontConv().converters[name], FontConv().converters[name]   # separate state (sakal)
    for data in runs:
        want = a.to_unicode(data)
        pieces = tracked.tracked_to_unicode(b, data)
        got = ''.join(p for p, _ in pieces)
        st['runs'] += 1; st['in_chars'] += len(data); st['out_chars'] += len(got)
        if got != want:
            st['MISMATCH'] += 1
            if len(ex) < 2: ex.append((data[:60], want[:60], got[:60]))
        if any(p and not src for p, src in pieces): st['piece_without_source'] += 1
        if len(pieces) == 1 and len(data) > 1 and pieces[0][1] == tuple(range(len(data))) and len(got) > 1: st['run_level'] += 1
        covered = set(i for _, src in pieces for i in src)
        st['in_chars_unattributed'] += sum(1 for i, c in enumerate(data) if i not in covered and not c.isspace())
        # granularity: chars per piece
        st['max_piece_src'] = max(st['max_piece_src'], max((len(s) for _, s in pieces), default=0))

print('== testdata ==')
for name in DEVA:
    data = open(os.path.join(I2U, 'testdata', name), encoding='utf8').read()
    for mode, runs in (('file', [data]), ('lines', data.splitlines(True))):
        st, ex = collections.Counter(), []
        check(name, runs, st, ex)
        print(f"{name:18s} {mode:5s} runs={st['runs']:5d} mismatch={st['MISMATCH']} no_src={st['piece_without_source']} "
              f"run_level={st['run_level']} unattributed_in={st['in_chars_unattributed']} max_piece_src={st['max_piece_src']}")
        for e in ex: print('     ', e)

print('== corpus runs (R grouping) ==')
runs = collections.defaultdict(list)
for path in open('corpus.txt').read().split():
    doc = pymupdf.open(path); f = ToUnicodeFixer(); f.fix_document(doc)
    for page in doc:
        for b in page.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                groups = []
                for s in l['spans']:
                    if not s['text']: continue
                    if groups and groups[-1][0] == s['font']: groups[-1][1] += s['text']
                    else: groups.append([s['font'], s['text']])
                for font, text in groups:
                    clean = re.sub(r'^[A-Z]{6}\+', '', font)
                    conv = get_font_converter(f.fixed_font_names.get(clean, clean)) or get_font_converter(clean)
                    if conv: runs[conv].append(text)
for name, rs in runs.items():
    st, ex = collections.Counter(), []
    check(name, rs, st, ex)
    print(f"{name:18s} runs={st['runs']:5d} chars={st['in_chars']:6d} mismatch={st['MISMATCH']} no_src={st['piece_without_source']} "
          f"unattributed_in={st['in_chars_unattributed']} max_piece_src={st['max_piece_src']}")
    for e in ex: print('     ', e)
