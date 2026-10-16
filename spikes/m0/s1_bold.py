import sys, os, collections, pymupdf
sys.path.insert(0, '.'); sys.argv = ['x']
exec(open('s1_join.py').read().split('tot = collections.Counter()')[0])
tab = collections.Counter(); fontflag = collections.Counter()
for path in open('corpus.txt').read().split():
    doc = pymupdf.open(path); ToUnicodeFixer().fix_document(doc)
    for pno in range(min(8, doc.page_count)):
        _, _, _, _, joined = join_page(doc[pno])
        for c, t, sp in joined:
            stroke_copy = 1 in t['span'].get('copy_types', [])
            lw = t['span'].get('linewidth')
            tab[(os.path.basename(path)[:14], 'stroke_copy' if stroke_copy else 'fill_only', 'cf_bold' if sp['char_flags'] & 8 else 'cf_-', 'font_bold' if sp['flags'] & 16 else 'nameflag_-')] += 1
for k, v in sorted(tab.items()): print(f'{v:6d}', k)
