"""Orchestration.

Routing policy, which is the substance of this module:

* Route **per page, not per document**. A single PDF is routinely part digital
  and part scan -- someone signs page 2, scans it, and staples it back on. A
  document-level decision either OCRs 4 clean pages for nothing or misses the
  scanned one entirely.
* OCR is a **fallback, never the default**. Rendering and recognising a page
  costs ~1-3 seconds against ~10ms for a text layer, so on a batch of 500
  resumes indiscriminate OCR is the difference between a minute and an hour.
* On `SUSPECT` pages, run **both** and keep the better one. This is the case
  the old `len < 50` check could not express: text exists, but might be junk.
  Native text wins ties because it is exact where OCR is probabilistic.
"""

from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from . import docx_reader, pdf_native, pdf_ocr, quality
from .layout import blocks_to_text, merge_paragraphs, order_blocks
from .sections import assign_sections
from .types import (Block, DocFormat, ExtractionResult, Method, PageReport,
                    QualityReport, Table, Verdict)


@dataclass
class Config:
    dpi: int = 300
    lang: str = "eng"
    force: Optional[str] = None     # None | "native" | "ocr"
    extract_tables: bool = True
    ocr_retry: bool = True
    max_pages: int = 12             # resumes are 1-3 pages; more means something odd
    workers: int = 4


# ---------------------------------------------------------------------------
# format sniffing


def sniff_format(path: str) -> DocFormat:
    """Identify by magic bytes, not extension.

    Users rename files. `resume.pdf` that is really a DOCX, and `resume.docx`
    that is really a PDF, both turn up in any real applicant pool. Trusting the
    extension turns those into hard crashes.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return DocFormat.UNKNOWN

    if head.startswith(b"%PDF"):
        return DocFormat.PDF
    if head.startswith(b"PK\x03\x04"):
        return DocFormat.DOCX if docx_reader.is_docx(path) else DocFormat.UNKNOWN
    if head.startswith(b"\xd0\xcf\x11\xe0"):   # OLE2 compound file
        return DocFormat.DOC_LEGACY
    return DocFormat.UNKNOWN


# ---------------------------------------------------------------------------
# fingerprints (duplicate detection)


def _normalise_for_hash(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def exact_fingerprint(text: str) -> str:
    return hashlib.sha256(_normalise_for_hash(text).encode()).hexdigest()[:32]


def near_fingerprint(text: str, bits: int = 64) -> str:
    """SimHash over token shingles — catches the same resume re-exported.

    Exact hashing misses the common case: the same CV saved from Word vs from
    Canva differs by a few whitespace and bullet characters. SimHash gives a
    Hamming distance instead, so near-duplicates stay detectable.
    """
    tokens = _normalise_for_hash(text).split()
    if not tokens:
        return "0" * (bits // 4)
    shingles = ([" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
                or tokens)
    vec = [0] * bits
    for sh in shingles:
        h = int(hashlib.md5(sh.encode()).hexdigest(), 16)
        for i in range(bits):
            vec[i] += 1 if (h >> i) & 1 else -1
    val = 0
    for i in range(bits):
        if vec[i] > 0:
            val |= 1 << i
    return f"{val:0{bits // 4}x}"


def hamming(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return 64


# ---------------------------------------------------------------------------
# PDF


def _extract_pdf(path: str, cfg: Config, result: ExtractionResult) -> None:
    doc = pdf_native.open_pdf(path)
    if doc.needs_pass:
        raise ValueError("PDF is password-protected")

    n_pages = min(len(doc), cfg.max_pages)
    if len(doc) > cfg.max_pages:
        result.warnings.append(
            f"document has {len(doc)} pages; processing first {cfg.max_pages} "
            f"(unusual for a resume — check this is not a portfolio)"
        )

    all_blocks: List[Block] = []
    used_native = used_ocr = False

    for pno in range(n_pages):
        page = doc[pno]
        page_no = pno + 1
        w, _h = pdf_native.page_dimensions(page)
        warnings: List[str] = []

        # --- native pass
        nat_blocks: List[Block] = []
        nat_q: Optional[QualityReport] = None
        if cfg.force != "ocr":
            t0 = time.perf_counter()
            nat_blocks = pdf_native.page_blocks(page, page_no)
            nat_blocks, nat_cols, nat_gut = order_blocks(nat_blocks, w)
            nat_q = quality.assess(blocks_to_text(nat_blocks), 1, f"p{page_no} native")
            result.timings_ms["native"] = result.timings_ms.get("native", 0.0) + \
                (time.perf_counter() - t0) * 1000

        if pdf_native.page_is_image_only(page):
            warnings.append(f"page {page_no}: no text layer but images present — scanned page")

        # --- routing decision
        need_ocr = cfg.force == "ocr" or (
            cfg.force != "native"
            and nat_q is not None
            and nat_q.verdict in (Verdict.EMPTY, Verdict.BAD, Verdict.SUSPECT)
        )

        chosen = nat_blocks
        ncols, gutter = (nat_cols, nat_gut) if nat_blocks else (0, None)
        method = Method.NATIVE
        ocr_conf: Optional[float] = None
        ocr_psm: Optional[int] = None
        final_q = nat_q

        if need_ocr:
            t0 = time.perf_counter()
            try:
                ocr_res, ocr_warn = pdf_ocr.ocr_page(page, page_no, dpi=cfg.dpi,
                                                     lang=cfg.lang,
                                                     allow_retry=cfg.ocr_retry)
                warnings.extend(ocr_warn)
                ocr_blocks, ocr_cols, ocr_gut = order_blocks(
                    ocr_res.blocks, w, gutter=ocr_res.gutter)
                ocr_q = quality.assess(blocks_to_text(ocr_blocks), 1, f"p{page_no} ocr")

                if nat_q is None or nat_q.verdict in (Verdict.EMPTY, Verdict.BAD):
                    take_ocr = True
                    why = "native text layer unusable"
                else:
                    take_ocr = quality.better_of(nat_q, ocr_q)
                    why = (f"OCR scored higher ({ocr_q.score:.2f} vs "
                           f"{nat_q.score:.2f})" if take_ocr else
                           f"native retained ({nat_q.score:.2f} vs {ocr_q.score:.2f})")

                if take_ocr:
                    chosen, final_q = ocr_blocks, ocr_q
                    ncols, gutter = ocr_cols, ocr_gut
                    method = Method.OCR if (nat_q is None or nat_q.verdict == Verdict.EMPTY) \
                        else Method.NATIVE_OCR_PICKED
                    ocr_conf, ocr_psm = ocr_res.mean_confidence, ocr_res.psm
                else:
                    method = Method.NATIVE_OCR_PICKED
                warnings.append(f"page {page_no}: OCR ran — {why}")
            except Exception as exc:
                warnings.append(f"page {page_no}: OCR failed ({exc}); keeping native text")
            result.timings_ms["ocr"] = result.timings_ms.get("ocr", 0.0) + \
                (time.perf_counter() - t0) * 1000

        # --- tables
        page_tables: List[Table] = []
        if cfg.extract_tables and method != Method.OCR:
            page_tables = pdf_native.extract_tables(path, page_no)
            pdf_native.mark_table_blocks(chosen, page_tables)
            result.tables.extend(page_tables)

        if method in (Method.OCR, Method.NATIVE_OCR_PICKED):
            used_ocr = True
        if method in (Method.NATIVE, Method.NATIVE_OCR_PICKED):
            used_native = True

        if ncols == 2:
            warnings.append(f"page {page_no}: two-column layout detected "
                            f"(gutter x={gutter[0]:.0f}-{gutter[1]:.0f}pt) — "
                            f"blocks reordered column-major")

        all_blocks.extend(chosen)
        result.pages.append(PageReport(
            page=page_no, method=method, n_blocks=len(chosen), n_columns=ncols,
            gutter=gutter, char_count=sum(len(b.text) for b in chosen),
            quality=final_q, ocr_confidence=ocr_conf, ocr_psm=ocr_psm,
            warnings=warnings,
        ))
        result.warnings.extend(warnings)

    result.links = pdf_native.extract_links(doc)
    doc.close()

    result.blocks = all_blocks
    if used_native and used_ocr:
        result.method = Method.NATIVE_OCR_PICKED
    elif used_ocr:
        result.method = Method.OCR
    elif used_native:
        result.method = Method.NATIVE
    else:
        result.method = Method.NONE


# ---------------------------------------------------------------------------
# entry points


def extract(path: str | Path, cfg: Optional[Config] = None) -> ExtractionResult:
    """Extract one document. Never raises — failures land in `result.error`.

    Batch callers should not have to wrap every document in try/except; a
    corrupt file in position 37 of 500 must not take down the run.
    """
    cfg = cfg or Config()
    path = str(path)
    t0 = time.perf_counter()

    fmt = sniff_format(path)
    result = ExtractionResult(path=path, doc_format=fmt, method=Method.NONE, text="")

    ext = Path(path).suffix.lower()
    if (ext == ".pdf" and fmt == DocFormat.DOCX) or (ext == ".docx" and fmt == DocFormat.PDF):
        result.warnings.append(
            f"extension is {ext} but content is {fmt.value} — trusting content"
        )

    try:
        if fmt == DocFormat.PDF:
            _extract_pdf(path, cfg, result)
        elif fmt == DocFormat.DOCX:
            blocks, tables, links, warns = docx_reader.extract(path)
            result.blocks, result.tables = blocks, tables
            result.links, result.method = links, Method.DOCX
            result.warnings.extend(warns)
            result.pages.append(PageReport(
                page=1, method=Method.DOCX, n_blocks=len(blocks), n_columns=1,
                gutter=None, char_count=sum(len(b.text) for b in blocks),
            ))
        elif fmt == DocFormat.DOC_LEGACY:
            raise ValueError(
                "legacy .doc format — convert first: "
                "soffice --headless --convert-to docx file.doc"
            )
        else:
            raise ValueError("unrecognised file type (not PDF or DOCX)")

        result.blocks = merge_paragraphs(result.blocks)
        result.text = blocks_to_text(result.blocks)
        result.sections = assign_sections(result.blocks)
        result.quality = quality.assess(result.text, max(1, len(result.pages)))
        result.exact_fingerprint = exact_fingerprint(result.text)
        result.near_fingerprint = near_fingerprint(result.text)

        if result.links:
            result.text += "\n\n" + "\n".join(result.links)

    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"

    result.timings_ms["total"] = (time.perf_counter() - t0) * 1000
    return result


def extract_batch(paths: Sequence[str | Path], cfg: Optional[Config] = None
                  ) -> List[ExtractionResult]:
    """Extract many documents in parallel.

    Threads, not processes: the expensive work is tesseract and MuPDF, both of
    which release the GIL. Threads keep memory flat and avoid pickling results
    across process boundaries.
    """
    cfg = cfg or Config()
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        return list(pool.map(lambda p: extract(p, cfg), paths))


def find_duplicates(results: Sequence[ExtractionResult], max_distance: int = 3
                    ) -> List[tuple]:
    """(path_a, path_b, distance) for documents that are the same resume.

    Distance 0 means byte-identical after normalisation; 1-6 means the same CV
    re-exported or lightly edited. Worth surfacing before ranking: the same
    candidate applying twice under two filenames otherwise occupies two slots.
    """
    out = []
    ok = [r for r in results if r.ok]
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            a, b = ok[i], ok[j]
            d = 0 if a.exact_fingerprint == b.exact_fingerprint else \
                hamming(a.near_fingerprint, b.near_fingerprint)
            if d <= max_distance:
                out.append((a.path, b.path, d))
    return sorted(out, key=lambda t: t[2])
