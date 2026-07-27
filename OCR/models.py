"""Core data model.

Everything the pipeline produces is one of these objects. The design rule:
*never return a bare string*. A downstream ranker needs to know where text came
from and how much to trust it, and a bare string throws that away.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

BBox = Tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points, origin top-left


class DocFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC_LEGACY = "doc"
    UNKNOWN = "unknown"


class Method(str, Enum):
    """How a page's text was obtained."""

    NATIVE = "native"          # embedded text layer (PyMuPDF)
    OCR = "ocr"                # rasterised + tesseract
    NATIVE_OCR_PICKED = "native+ocr(picked)"  # both ran, better one kept
    DOCX = "docx"              # OOXML walk
    NONE = "none"              # nothing usable


class Column(int, Enum):
    FULL = -1   # spans the gutter (headers, section rules, full-width bullets)
    LEFT = 0
    RIGHT = 1


class Verdict(str, Enum):
    GOOD = "good"        # trust it
    SUSPECT = "suspect"  # plausible but flagged -> run OCR and compare
    BAD = "bad"          # unusable -> OCR
    EMPTY = "empty"      # nothing at all -> OCR


@dataclass
class Block:
    """A contiguous run of text with a known position on a known page."""

    text: str
    page: int
    bbox: BBox
    source: str                      # "pymupdf" | "tesseract" | "docx:body" | "docx:textbox" | ...
    column: int = Column.FULL
    order: int = 0                   # index in reconstructed reading order
    confidence: Optional[float] = None  # 0-100, OCR only
    font_size: Optional[float] = None
    bold: bool = False
    in_table: bool = False
    section: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Table:
    page: int
    bbox: Optional[BBox]
    rows: List[List[str]]
    source: str = "pdfplumber"

    @property
    def as_text(self) -> str:
        return "\n".join(" | ".join(c or "" for c in r) for r in self.rows)

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "as_text": self.as_text}


@dataclass
class QualitySignal:
    name: str
    value: float
    penalty: float
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualityReport:
    """Explainable replacement for `len(text) < 50`."""

    score: float                 # 0.0 - 1.0
    verdict: Verdict
    signals: List[QualitySignal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "verdict": self.verdict.value,
            "signals": [s.to_dict() for s in self.signals],
        }

    @property
    def reasons(self) -> List[str]:
        return [s.note for s in self.signals if s.penalty > 0]


@dataclass
class PageReport:
    page: int
    method: Method
    n_blocks: int
    n_columns: int
    gutter: Optional[Tuple[float, float]]
    char_count: int
    quality: Optional[QualityReport] = None
    ocr_confidence: Optional[float] = None
    ocr_psm: Optional[int] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["method"] = self.method.value
        d["quality"] = self.quality.to_dict() if self.quality else None
        return d


@dataclass
class ExtractionResult:
    path: str
    doc_format: DocFormat
    method: Method
    text: str
    blocks: List[Block] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    sections: Dict[str, str] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    pages: List[PageReport] = field(default_factory=list)
    quality: Optional[QualityReport] = None
    exact_fingerprint: str = ""
    near_fingerprint: str = ""
    warnings: List[str] = field(default_factory=list)
    timings_ms: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())

    @property
    def confidence(self) -> float:
        """Single 0-1 number a downstream ranker can gate on."""
        if self.error or not self.text.strip():
            return 0.0
        base = self.quality.score if self.quality else 0.5
        ocr_pages = [p for p in self.pages if p.ocr_confidence is not None]
        if ocr_pages:
            mean_ocr = sum(p.ocr_confidence for p in ocr_pages) / len(ocr_pages)
            base = 0.6 * base + 0.4 * (mean_ocr / 100.0)
        return round(max(0.0, min(1.0, base)), 3)

    def to_dict(self, include_blocks: bool = True) -> Dict[str, Any]:
        return {
            "path": self.path,
            "doc_format": self.doc_format.value,
            "method": self.method.value,
            "confidence": self.confidence,
            "char_count": len(self.text),
            "n_blocks": len(self.blocks),
            "n_tables": len(self.tables),
            "sections": self.sections,
            "links": self.links,
            "quality": self.quality.to_dict() if self.quality else None,
            "pages": [p.to_dict() for p in self.pages],
            "exact_fingerprint": self.exact_fingerprint,
            "near_fingerprint": self.near_fingerprint,
            "warnings": self.warnings,
            "timings_ms": {k: round(v, 1) for k, v in self.timings_ms.items()},
            "error": self.error,
            "blocks": [b.to_dict() for b in self.blocks] if include_blocks else [],
            "tables": [t.to_dict() for t in self.tables],
            "text": self.text,
        }
