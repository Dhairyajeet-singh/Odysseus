# OCR/__init__.py
"""Stage 1: documents in, structured provenance-tagged text out."""

from .pipeline import Config, extract, extract_batch, find_duplicates
from .models import (Block, Column, DocFormat, ExtractionResult, Method,
                     PageReport, QualityReport, Table, Verdict)

__all__ = [
    "Config", "extract", "extract_batch", "find_duplicates",
    "Block", "Column", "DocFormat", "ExtractionResult", "Method",
    "PageReport", "QualityReport", "Table", "Verdict",
]