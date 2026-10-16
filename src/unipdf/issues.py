"""Issues (UP-IS-1), ported from cidpdf's Issue / IssueBag.

Library code records what it could not do here and logs it; it never prints
(UP-IS-2)."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

logger = logging.getLogger("unipdf")

Severity = Literal["info", "warning", "error"]

# the codes v1 raises
REPAIR_FAILED = "repair_failed"
NO_TEXT_LAYER = "no_text_layer"
NO_CONVERTER = "no_converter"
UNCONVERTED_CHAR = "unconverted_char"
CONVERTER_ERROR = "converter_error"
UNJOINED_GLYPH = "unjoined_glyph"
ACTUAL_TEXT = "actual_text"
JOINED_WORDS = "joined_words"
PROVENANCE_UNAVAILABLE = "provenance_unavailable"
EXTRACTION_MISMATCH = "extraction_mismatch"


@dataclass
class Issue:
    id: str
    severity: Severity
    code: str
    message: str
    page: int | None = None  # 0-based
    font: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IssueBag:
    def __init__(self) -> None:
        self._issues: list[Issue] = []

    def add(
        self,
        *,
        severity: Severity,
        code: str,
        message: str,
        page: int | None = None,
        font: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Issue:
        issue = Issue(
            id=f"issue:{len(self._issues) + 1:06d}",
            severity=severity,
            code=code,
            message=message,
            page=page,
            font=font,
            bbox=bbox,
            context=context or {},
        )
        self._issues.append(issue)
        log = logger.warning if severity != "info" else logger.debug
        log("%s: %s", code, message)
        return issue

    def __len__(self) -> int:
        return len(self._issues)

    def all(self) -> list[Issue]:
        return list(self._issues)

    def by_code(self, code: str) -> list[Issue]:
        return [issue for issue in self._issues if issue.code == code]

    def group_by(self, name: str) -> dict[Any, list[Issue]]:
        grouped: dict[Any, list[Issue]] = defaultdict(list)
        for issue in self._issues:
            grouped[getattr(issue, name)].append(issue)
        return dict(grouped)

    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self._issues)

    def to_list(self) -> list[dict[str, Any]]:
        return [issue.to_dict() for issue in self._issues]
