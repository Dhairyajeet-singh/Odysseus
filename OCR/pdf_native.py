"""Native (text-layer) PDF extraction.

Library choice, deliberately: **PyMuPDF**, not PyPDF2.

The old pipeline's fallback chain was pdfplumber -> PyPDF2 -> OCR. The middle
tier was dead weight: both libraries read the same embedded text layer, so if
pdfplumber returns nothing, PyPDF2 returns nothing too. It is a fallback that
cannot fall back.

PyMuPDF earns its place for a different reason: `get_text("dict")` returns
per-block bounding boxes, font sizes and style flags. That geometry is the raw
material for column detection and section detection. pdfplumber is retained for
one thing it does better -- ruled table extraction.
"""

from __future__ import annotations

from typing import List, Tuple

import fitz  # PyMuPDF

from .models import Block, Table

_BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit for bold


def open_pdf(path: str) -> fitz.Document:
    return fitz.open(path)


def page_blocks(page: "fitz.Page", page_no: int) -> List[Block]:
    """Text blocks with geometry and typography from the embedded text layer."""
    out: List[Block] = []
    data = page.get_text("dict")

    for raw in data.get("blocks", []):
        if raw.get("type") != 0:  # 1 == image block
            continue
        lines: List[str] = []
        sizes: List[float] = []
        bold_chars = 0
        total_chars = 0
        for ln in raw.get("lines", []):
            chunk = "".join(s.get("text", "") for s in ln.get("spans", []))
            for s in ln.get("spans", []):
                t = s.get("text", "")
                sizes.append(float(s.get("size", 0.0)))
                total_chars += len(t)
                if int(s.get("flags", 0)) & _BOLD_FLAG:
                    bold_chars += len(t)
            if chunk.strip():
                lines.append(chunk.rstrip())
        if not lines:
            continue
        out.append(Block(
            text="\n".join(lines),
            page=page_no,
            bbox=tuple(round(v, 2) for v in raw["bbox"]),  # type: ignore[arg-type]
            source="pymupdf",
            font_size=round(max(sizes), 2) if sizes else None,
            bold=(total_chars > 0 and bold_chars / total_chars > 0.6),
        ))
    return out


def page_is_image_only(page: "fitz.Page") -> bool:
    """No usable text layer, but ink on the page — the scanned-PDF signature."""
    has_text = bool(page.get_text("text").strip())
    has_images = bool(page.get_images(full=False))
    return (not has_text) and has_images


def page_dimensions(page: "fitz.Page") -> Tuple[float, float]:
    r = page.rect
    return float(r.width), float(r.height)


def extract_tables(path: str, page_no: int) -> List[Table]:
    """Ruled/structured tables via pdfplumber.

    Kept separate from the text stream on purpose. Table cell text is already
    present in the block stream, so emitting it twice would double-count skills
    for any candidate who formats their skills section as a grid. Instead the
    overlapping blocks get `in_table=True` and the structured rows are exposed
    alongside, letting a downstream consumer choose.
    """
    tables: List[Table] = []
    try:
        import pdfplumber
    except ImportError:
        return tables

    try:
        with pdfplumber.open(path) as pdf:
            if page_no - 1 >= len(pdf.pages):
                return tables
            page = pdf.pages[page_no - 1]
            found = page.find_tables()
            for t in found:
                try:
                    rows = t.extract()
                except Exception:
                    continue
                rows = [[(c or "").strip() for c in row] for row in rows if row]
                rows = [r for r in rows if any(r)]
                if len(rows) >= 2:
                    tables.append(Table(
                        page=page_no,
                        bbox=tuple(round(float(v), 2) for v in t.bbox),  # type: ignore[arg-type]
                        rows=rows,
                    ))
    except Exception:
        return tables
    return tables


def mark_table_blocks(blocks: List[Block], tables: List[Table]) -> None:
    """Flag blocks that sit inside a detected table region."""
    for t in tables:
        if not t.bbox:
            continue
        tx0, ty0, tx1, ty1 = t.bbox
        for b in blocks:
            bx0, by0, bx1, by1 = b.bbox
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if tx0 <= cx <= tx1 and ty0 <= cy <= ty1:
                b.in_table = True


def extract_links(doc: "fitz.Document") -> List[str]:
    """Hyperlink targets.

    Resumes routinely render a LinkedIn or GitHub profile as the word "LinkedIn"
    with the actual URL only in the link annotation. Text extraction alone loses
    it entirely.
    """
    seen: List[str] = []
    for page in doc:
        for link in page.get_links():
            uri = link.get("uri")
            if uri and uri not in seen:
                seen.append(uri)
    return seen
