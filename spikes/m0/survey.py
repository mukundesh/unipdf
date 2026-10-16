# Font survey: for sampled PDFs, list fonts (first 3 pages) -> converter resolution
import sys, os, re, random, json, collections, pymupdf
sys.path.insert(0, '/Users/mukund/orgpedia/Try/indic2unicode')
import logging; logging.disable(logging.WARNING)
from indic2unicode.fontconv import FontConv
from indic2unicode.tools.fix_tounicode import get_font_converter
fc = FontConv()
names = set(fc.converters)
def strip(n): return re.sub(r'^[A-Z]{6}\+', '', n)
def resolve(n):
    c = strip(n)
    g = get_font_converter(c)
    if g: return 'R:' + g   # converter only valid if repaired
    for k in (n, c, c.split(',')[0], c.split('-')[0]):
        if k in names: return k
    key = re.sub(r'[\s\-_,]+', '', c.split(',')[0]).lower()
    for k in names:
        if re.sub(r'[\s\-_,]+', '', k).lower() == key: return k
    return None
roots = sys.argv[1:]
files = []
for r in roots:
    fs = [os.path.join(d, f) for d, _, ff in os.walk(r) for f in ff if f.endswith('.pdf')]
    random.seed(1); random.shuffle(fs); files += fs[:25]
out = collections.defaultdict(list)
for p in files:
    try:
        doc = pymupdf.open(p)
        fonts = {f[3] for i in range(min(3, doc.page_count)) for f in doc.get_page_fonts(i)}
    except Exception as e:
        continue
    for f in fonts:
        conv = resolve(f)
        if conv: out[conv].append(p)
for k, v in sorted(out.items(), key=lambda kv: -len(kv[1])):
    print(f'{k:28s} {len(v):4d}  {v[0]}')
json.dump(out, open('survey.json', 'w'))
