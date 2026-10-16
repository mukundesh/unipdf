"""Visual rows (UP-LY-2).

MuPDF starts a new `rawdict` line wherever a justified gap is wide, so one
printed line can arrive as several. Consecutive lines of one block, both
horizontal, whose baselines differ by at most `tol` × font size are one row,
ordered left to right. Conversion has already run on the `rawdict` lines; a
row only changes how they are laid out.
"""

from __future__ import annotations

from unipdf.pdf.glyphs import RawLine

ROW_TOLERANCE = 0.2


def _horizontal(line: RawLine) -> bool:
    return line.wmode == 0 and abs(line.dir[0] - 1) < 1e-3 and abs(line.dir[1]) < 1e-3


def visual_rows(lines: list[RawLine], tol: float = ROW_TOLERANCE) -> list[list[RawLine]]:
    """rows of non-empty lines, in the order of their first line"""
    rows: list[list[RawLine]] = []
    for line in lines:
        if not line.glyphs:
            continue
        if rows:
            first = rows[-1][0]
            last = rows[-1][-1]
            if (
                last.block == line.block
                and _horizontal(first)
                and _horizontal(line)
                and first.baseline is not None
                and line.baseline is not None
                and abs(line.baseline - first.baseline) <= tol * max(first.size, line.size)
            ):
                rows[-1].append(line)
                continue
        rows.append([line])
    for row in rows:
        row.sort(key=lambda ln: ln.bbox[0])
    return rows
