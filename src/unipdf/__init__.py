"""unipdf: Hindi and Marathi text from PDFs as Unicode, with word boxes.

    import unipdf
    doc = unipdf.open("in.pdf")
    doc.text()
    for w in doc.iter_words():
        w.text, w.bbox, w.size
    unipdf.convert("chanakya", text)  # text that is not in a PDF
"""

__version__ = "0.2.2"

from unipdf.convert.strings import convert, convert_with_provenance, converter_names
from unipdf.pipeline import PasswordRequired, read_document

open = read_document  # the library's entry point (UP-API-1)

__all__ = [
    "PasswordRequired",
    "__version__",
    "convert",
    "convert_with_provenance",
    "converter_names",
    "open",
    "read_document",
]
