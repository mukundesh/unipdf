import sys; sys.argv = sys.argv[:1] + sys.argv[1:]
args = sys.argv[1:]
exec(open('s3.py').read().split("if __name__")[0])
path, pno, out = args[0], int(args[1]), args[2]
clip = pymupdf.Rect(*map(float, args[3].split(','))) if len(args) > 3 else None
doc = pymupdf.open(path); ToUnicodeFixer().fix_document(doc)
page = doc[pno]
words = page_words(doc, page)
fonts = collections.Counter(w['font'] for w in words); print(fonts.most_common(3))
for w in words:
    page.draw_rect(pymupdf.Rect(w['A']), color=(1, 0, 0), width=0.3)
    if w['K']: page.draw_rect(pymupdf.Rect(w['K']), color=(0, 0, 1), width=0.3)
pix = page.get_pixmap(dpi=150, clip=clip); pix.save(out); print(out, pix.width, pix.height)
