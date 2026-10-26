"""The parity corpus (tests/corpus/manifest.yaml) for tests and tools."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

CORPUS = Path(__file__).parent / "corpus"


def manifest() -> dict:
    with open(CORPUS / "manifest.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_pdf(entry: dict) -> Path | None:
    """the corpus copy, else the source path if it is still the same file"""
    if entry.get("file"):
        path = CORPUS / entry["file"]
        if path.exists():
            return path
    src = Path(entry["source"]).expanduser()  # sources are written with ~
    if src.exists() and hashlib.sha256(src.read_bytes()).hexdigest() == entry["sha256"]:
        return src
    return None


def corpus_pdfs():
    for entry in manifest()["pdfs"]:
        yield entry, resolve_pdf(entry)


def golden_paths(pdf_id: str) -> tuple[Path, Path]:
    return CORPUS / "golden" / f"{pdf_id}.txt", CORPUS / "golden" / f"{pdf_id}.json"
