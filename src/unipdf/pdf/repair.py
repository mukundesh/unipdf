"""ToUnicode repair (UP-RP-1..4), as R runs it.

`fix_document` repairs the whole document in one call and the absorbed code
is not edited (D-16), so a failure is per document, not per font: the
document then goes on unrepaired, as R does."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from unipdf.i2u.fix_tounicode import ToUnicodeFixer
from unipdf.issues import REPAIR_FAILED, IssueBag


@dataclass
class RepairResult:
    # the name the PDF carries -> the name it was repaired as; None when
    # repair was not run or failed
    repaired: dict[str, str] | None
    error: str | None = None


def repair(doc: pymupdf.Document, issues: IssueBag | None = None) -> RepairResult:
    fixer = ToUnicodeFixer()
    try:
        fixer.fix_document(doc)
    except Exception as e:  # noqa: BLE001 - UP-RP-4: continue unrepaired
        error = f"{type(e).__name__}: {e}"
        if issues is not None:
            issues.add(severity="warning", code=REPAIR_FAILED,
                       message=f"ToUnicode repair failed, continuing unrepaired: {error}")
        return RepairResult(None, error)
    return RepairResult(dict(fixer.fixed_font_names))
