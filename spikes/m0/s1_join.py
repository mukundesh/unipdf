# S1 v2: sequence-aware join of rawdict chars to texttrace entries (after repair)
import sys, os, collections, pymupdf
sys.path.insert(0, '/Users/mukund/orgpedia/Try/indic2unicode')
import logging; logging.disable(logging.WARNING)
from indic2unicode.tools.fix_tounicode import ToUnicodeFixer
TOL = 0.01

def trace_entries(page):
    """flat texttrace entries; spans that repeat an earlier span glyph for glyph
       (fill then stroke, or an overprint) are marked as copies"""
    T, seen, copies = [], {}, collections.Counter()
    for s in page.get_texttrace():
        sig = tuple((u, g, round(o[0], 2), round(o[1], 2)) for u, g, o, _ in s['chars'])
        orig = seen.get(sig)
        if orig is not None:
            copies[(orig['type'], s['type'])] += len(sig)
            orig.setdefault('copy_types', []).append(s['type']); continue
        seen[sig] = s
        for u, g, o, bb in s['chars']:
            T.append(dict(u=u, gid=g, o=o, span=s, used=False))
    return T, copies

def near(a, b): return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL

def join_page(page, rd=None):
    T, copies = trace_entries(page)
    idx = collections.defaultdict(list)
    for i, t in enumerate(T): idx[(round(t['o'][0]), round(t['o'][1]))].append(i)
    def by_origin(c):
        x, y = round(c['origin'][0]), round(c['origin'][1])
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in idx.get((x + dx, y + dy), ()):
                    if not T[i]['used'] and T[i]['u'] == ord(c['c']) and near(T[i]['o'], c['origin']): return i
    st = collections.Counter(); misses = []; joined = []
    prev = -1
    for b in (rd or page.get_text('rawdict'))['blocks']:
        for l in b.get('lines', []):
            for sp in l['spans']:
                for c in sp['chars']:
                    st['chars'] += 1
                    if c['synthetic']: st['synthetic'] += 1; continue
                    succ = prev + 1
                    while succ < len(T) and T[succ]['used']: succ += 1
                    seq_ok = succ < len(T) and T[succ]['u'] == ord(c['c'])
                    i = None
                    if seq_ok and (near(T[succ]['o'], c['origin']) or T[succ]['gid'] == -1): i, how = succ, 'seq+origin' if near(T[succ]['o'], c['origin']) else 'seq_only'
                    if i is None:
                        i = by_origin(c); how = 'origin'
                    if i is None and seq_ok: i, how = succ, 'seq_only'
                    if i is None:
                        j, k = succ, 0
                        while j < len(T) and k < 8:
                            if not T[j]['used']:
                                if T[j]['u'] == ord(c['c']): i, how = j, 'lookahead'; break
                                k += 1
                            j += 1
                    if i is None:
                        for j in range(len(T)):
                            if not T[j]['used'] and T[j]['u'] == 0xFFFD and near(T[j]['o'], c['origin']): i, how = j, 'origin_unicode_fffd'; break
                    if i is None:
                        st['miss'] += 1; misses.append((c['c'], c['origin'])); continue
                    st[how] += 1
                    if how == 'seq_only':
                        st['seq_only_cont' if T[i]['gid'] == -1 else 'seq_only_moved'] += 1
                        if T[i]['gid'] != -1: st['moved_dx_%s' % ('lt1' if abs(T[i]['o'][0]-c['origin'][0]) < 1 else 'ge1')] += 1
                    T[i]['used'] = True; prev = i; joined.append((c, T[i], sp))
    left = [t for t in T if not t['used']]
    for t in left:
        k = 'tt_left_space' if t['u'] == 32 else ('tt_left_invisible' if t['span']['type'] == 3 else 'tt_left_other')
        st[k] += 1
    return st, misses, left, copies, joined

tot = collections.Counter(); allcopies = collections.Counter()
for path in open('corpus.txt').read().split():
    doc = pymupdf.open(path); ToUnicodeFixer().fix_document(doc)
    fst = collections.Counter(); ex = []; exl = []
    for pno in range(min(8, doc.page_count)):
        st, misses, left, copies, _ = join_page(doc[pno])
        fst += st; allcopies += copies
        ex += [(pno,) + m for m in misses[:2]]; exl += [(pno, chr(t['u']), t['gid'], t['span']['type'], t['span']['font']) for t in left if t['u'] != 32][:2]
    tot += fst
    real = fst['chars'] - fst['synthetic']
    print(f"{os.path.basename(path):28s} real={real:6d} joined={(real - fst['miss'])/max(real,1):8.4%} " + ' '.join(f'{k}={v}' for k, v in sorted(fst.items()) if k not in ('chars',)))
    if ex: print('     miss', ex[:3])
    if exl: print('     left', exl[:3])
real = tot['chars'] - tot['synthetic']
print('\nTOTAL join rate %.4f%%' % (100 * (real - tot['miss']) / real), dict(tot))
import json; json.dump(dict(tot), open('s1_total.json','w'))
print('copy passes (orig type, copy type) -> glyphs', dict(allcopies))
