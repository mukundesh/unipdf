# S3: are rawdict char boxes good enough for word boxes? Compare against
# glyph ink boxes (embedded font outlines via fontTools, gid via S1 join).
import sys, os, io, re, collections, json, pymupdf
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
sys.path.insert(0, '.'); sys.argv = ['x']
exec(open('s1_join.py').read().split('tot = collections.Counter()')[0])

class InkBoxes:
    def __init__(self, doc, page):
        self.fonts = {}
        for xref, ext, typ, basefont, refname, enc in page.get_fonts():
            name = re.sub(r'^[A-Z]{6}\+', '', basefont)
            try:
                _, ext2, _, buf = doc.extract_font(xref)
                if not buf: continue
                tt = TTFont(io.BytesIO(buf), fontNumber=0, lazy=True)
                self.fonts.setdefault(name, []).append((tt, tt.getGlyphSet(), tt.getGlyphOrder(), tt['head'].unitsPerEm, {}))
            except Exception as e:
                pass
    def em_box(self, fontname, gid):
        for tt, gs, order, upm, cache in self.fonts.get(re.sub(r'^[A-Z]{6}\+', '', fontname), []):
            if gid in cache: return cache[gid]
            if 0 <= gid < len(order):
                pen = BoundsPen(gs); gs[order[gid]].draw(pen)
                b = None if pen.bounds is None else tuple(v / upm for v in pen.bounds)
                cache[gid] = b
                return b
        return 'nofont'

def union(bs):
    bs = [b for b in bs if b]
    if not bs: return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
def area(b): return max(0, b[2]-b[0]) * max(0, b[3]-b[1])
def inter(a, b): return (max(a[0],b[0]), max(a[1],b[1]), min(a[2],b[2]), min(a[3],b[3]))

def page_words(doc, page):
    """words = runs of non-space rawdict chars within a rawdict line"""
    ink = InkBoxes(doc, page)
    rd = page.get_text('rawdict')
    _, _, _, _, joined = join_page(page, rd)
    jmap = {id(c): t for c, t, sp in joined}
    words = []
    for b in rd['blocks']:
        for l in b.get('lines', []):
            cur = None
            for sp in l['spans']:
                for c in sp['chars']:
                    if c['c'].isspace():
                        cur = None; continue
                    if cur is None:
                        cur = dict(chars=[], raw=[], ink=[], tt=[], size=sp['size'], font=sp['font'], line=l['bbox']); words.append(cur)
                    cur['chars'].append(c['c']); cur['raw'].append(c['bbox'])
                    t = jmap.get(id(c))
                    if t is not None and t['gid'] >= 0:
                        eb = ink.em_box(t['span']['font'], t['gid'])
                        if eb == 'nofont': cur['nofont'] = True
                        elif eb:
                            s, (ox, oy) = t['span']['size'], t['o']
                            cur['ink'].append((ox + eb[0]*s, oy - eb[3]*s, ox + eb[2]*s, oy - eb[1]*s))
    for w in words:
        w['A'] = union(w['raw']); w['K'] = union(w['ink']); w['text'] = ''.join(w['chars'])
    return words

if __name__ == '__main__':
    tot = collections.Counter(); worst = []
    for path in open('corpus.txt').read().split():
        doc = pymupdf.open(path); ToUnicodeFixer().fix_document(doc)
        st = collections.Counter()
        for pno in range(min(5, doc.page_count)):
            words = page_words(doc, doc[pno])
            for w in words:
                st['words'] += 1
                if w.get('nofont') or not w['K']: st['no_ink'] += 1; continue
                A, K = w['A'], w['K']
                cov = area(inter(A, K)) / max(area(K), 1e-9)
                s = w['size']
                st['cov<0.98'] += cov < 0.98; st['cov<0.90'] += cov < 0.90
                st['ink_above>0.05s'] += (A[1] - K[1]) > 0.05 * s
                st['ink_below>0.05s'] += (K[3] - A[3]) > 0.05 * s
                st['ink_left>0.05s'] += (A[0] - K[0]) > 0.05 * s
                st['ink_right>0.05s'] += (K[2] - A[2]) > 0.05 * s
                # how much taller than ink the rawdict box is
                st['_slack_sum'] += ((A[3]-A[1]) - (K[3]-K[1])) / s
                if cov < 0.9 and len(worst) < 400: worst.append((os.path.basename(path), pno, w['text'], round(cov, 3), [round(v,1) for v in A], [round(v,1) for v in K], s))
            # inter-line overlap between rawdict word boxes of different lines that overlap horizontally
            for i, a in enumerate(words):
                for b in words[i+1:]:
                    if a['line'] == b['line'] or abs(a['A'][1]-b['A'][1]) < 0.5 * a['size']: continue
                    I = inter(a['A'], b['A'])
                    if I[2] > I[0] and I[3] > I[1]:
                        frac = (I[3]-I[1]) / min(a['A'][3]-a['A'][1], b['A'][3]-b['A'][1])
                        st['pairs_vertical_overlap'] += 1
                        st['pairs_overlap>20%'] += frac > 0.2
        tot += st
        n = st['words'] - st['no_ink']
        print(f"{os.path.basename(path):28s} words={st['words']:5d} no_ink={st['no_ink']:4d} cov<.98={st['cov<0.98']:4d} cov<.90={st['cov<0.90']:3d} "
              f"above={st['ink_above>0.05s']:4d} below={st['ink_below>0.05s']:4d} left={st['ink_left>0.05s']:3d} right={st['ink_right>0.05s']:3d} "
              f"slack={st['_slack_sum']/max(n,1):.2f}em  vpairs={st['pairs_vertical_overlap']} >20%={st['pairs_overlap>20%']}")
    print('TOTAL', dict(tot))
    json.dump(worst, open('s3_worst.json', 'w'), ensure_ascii=False)
