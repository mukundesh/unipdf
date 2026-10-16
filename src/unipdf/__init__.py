"""unipdf: Hindi and Marathi text from PDFs as Unicode, with word boxes.

    import unipdf
    doc = unipdf.open("in.pdf")
    doc.text()
    for w in doc.iter_words():
        w.text, w.bbox, w.size
"""

__version__ = "0.1.0"

from unipdf.pipeline import PasswordRequired, read_document

open = read_document  # the library's entry point (UP-API-1)

__all__ = ["PasswordRequired", "__version__", "open", "read_document"]
