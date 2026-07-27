"""OCR path: rasterise with PyMuPDF, recognise with tesseract.

Three deliberate differences from the old implementation.

1. **Rasterise with PyMuPDF, not pdf2image.** pdf2image shells out to poppler,
   which means a system binary that has to be installed separately and a
   subprocess per page. PyMuPDF is already a dependency for the native path and
   renders in-process. One fewer thing to get wrong in a README.

2. **`image_to_data`, not `image_to_string`.** Same OCR cost, but it returns
   per-word confidence and bounding boxes instead of a flat string. The boxes
   feed the same column-ordering code as the native path; the confidences give
   an honest per-page trust score. `image_to_string` throws all of that away.

3. **Adaptive retry.** If the first pass comes back weak, retry with a different
   page-segmentation mode and keep whichever result scores better. Bad scans are
   usually a segmentation problem, not a recognition problem.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional, Tuple

import fitz
import pytesseract
from PIL import Image, ImageOps

from .layout import _classify, detect_gutter
from .types import Block, Column

# 3 = fully automatic with orientation/script detection (handles columns itself)
# 4 = assume a single column of variable-sized text
# 6 = assume a single uniform block of text
_PSM_PRIMARY = 3
_PSM_RETRIES = (4, 6)
_MIN_WORD_CONF = 30.0     # drop words tesseract itself doubts
_RETRY_CONF_FLOOR = 72.0  # mean confidence below this triggers a retry
_RETRY_WORD_FLOOR = 60    # ...as does an implausibly short page


@dataclass
class OcrPage:
    blocks: List[Block]
    mean_confidence: float
    psm: int
    n_words: int
    gutter: Optional[Tuple[float, float]] = None


def render_page(page: "fitz.Page", dpi: int = 300, grayscale: bool = True) -> Image.Image:
    """Render a PDF page to a PIL image.

    300 DPI is the practical floor for 9-10pt body text, which is what resumes
    use. 150 DPI roughly halves OCR time and noticeably increases errors on
    small type; 600 quadruples cost for negligible gain on printed text.
    """
    cs = fitz.csGRAY if grayscale else fitz.csRGB
    pix = page.get_pixmap(dpi=dpi, colorspace=cs)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return ImageOps.autocontrast(img) if grayscale else img


def detect_rotation(img: Image.Image) -> int:
    """Best-effort page rotation via tesseract OSD; 0 if unavailable.

    Phone-photographed and badly-fed scans arrive sideways. OSD needs the
    optional `osd` traineddata, which is often missing, so failure is expected
    and non-fatal rather than an error.
    """
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        return int(osd.get("rotate", 0)) % 360
    except Exception:
        return 0


def _group_lines(words: List[dict], tol: float = 0.6) -> List[dict]:
    """Cluster words into lines by vertical overlap."""
    lines: List[dict] = []
    for w in sorted(words, key=lambda w: (w["bbox"][1], w["bbox"][0])):
        wy = (w["bbox"][1] + w["bbox"][3]) / 2
        wh = max(1.0, w["bbox"][3] - w["bbox"][1])
        for ln in reversed(lines[-4:]):
            if abs(wy - ln["cy"]) <= tol * max(wh, ln["h"]):
                ln["words"].append(w)
                bb, wb = ln["bbox"], w["bbox"]
                ln["bbox"] = [min(bb[0], wb[0]), min(bb[1], wb[1]),
                              max(bb[2], wb[2]), max(bb[3], wb[3])]
                ln["cy"] = (ln["bbox"][1] + ln["bbox"][3]) / 2
                ln["h"] = ln["bbox"][3] - ln["bbox"][1]
                break
        else:
            lines.append({"words": [w], "bbox": list(w["bbox"]), "cy": wy, "h": wh})
    return lines


def _ocr_once(img: Image.Image, page_no: int, scale: float, page_width: float,
              psm: int, lang: str = "eng") -> OcrPage:
    """Recognise a page and rebuild lines from *word* geometry.

    Deliberately ignores tesseract's own block/line hierarchy. On a scanned
    two-column resume, psm 3 groups a sidebar heading and an unrelated job
    title into one line -- reproducing, inside the OCR engine, exactly the
    column-fusion bug we fixed on the native path:

        SKILLS EXPERIENCE
        Python Senior Data Engineer, Acme Corp

    Word bounding boxes are reliable; only the grouping is wrong. So we take
    the words, run the same gutter detection used on the native path, split by
    column, and only then group into lines. One layout implementation now
    serves both paths, and neither can fuse columns.
    """
    cfg = f"--oem 1 --psm {psm}"
    data = pytesseract.image_to_data(
        img, lang=lang, config=cfg, output_type=pytesseract.Output.DICT
    )

    words: List[dict] = []
    for i in range(len(data["text"])):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < _MIN_WORD_CONF:
            continue
        x, y = data["left"][i], data["top"][i]
        w_, h_ = data["width"][i], data["height"][i]
        words.append({
            "text": txt,
            "conf": conf,
            "bbox": [x * scale, y * scale, (x + w_) * scale, (y + h_) * scale],
        })

    if not words:
        return OcrPage([], 0.0, psm, 0, None)

    # Column split from word geometry — a word box never straddles a gutter,
    # which makes words a cleaner input to detection than any grouped unit.
    probes = [Block(text=w["text"], page=page_no, bbox=tuple(w["bbox"]),
                    source="ocr-word") for w in words]
    gutter = detect_gutter(probes, page_width)

    # Group by vertical position first, then split a line only if it genuinely
    # carries words from *both* columns. Splitting per column up front tears
    # apart full-width header lines: a contact line's email lands in one block
    # and its phone number in another, which then sort into different bands.
    blocks: List[Block] = []
    all_confs: List[float] = []

    for ln in _group_lines(words):
        by_col: dict = {}
        for w in ln["words"]:
            probe = Block(text=w["text"], page=page_no,
                          bbox=tuple(w["bbox"]), source="ocr-word")
            col = _classify(probe, gutter, page_width) if gutter else Column.FULL
            by_col.setdefault(col, []).append(w)

        crosses = Column.LEFT in by_col and Column.RIGHT in by_col
        parts = ([(c, ws) for c, ws in by_col.items()] if crosses
                 else [(Column.FULL, ln["words"])])

        for col, ws in parts:
            ws = sorted(ws, key=lambda w: w["bbox"][0])
            text = " ".join(w["text"] for w in ws)
            if not text.strip():
                continue
            confs = [w["conf"] for w in ws]
            all_confs.extend(confs)
            xs = [w["bbox"] for w in ws]
            blocks.append(Block(
                text=text,
                page=page_no,
                bbox=(round(min(b[0] for b in xs), 2), round(min(b[1] for b in xs), 2),
                      round(max(b[2] for b in xs), 2), round(max(b[3] for b in xs), 2)),
                source=f"tesseract:psm{psm}",
                column=col,
                confidence=round(sum(confs) / len(confs), 2),
            ))

    mean_conf = sum(all_confs) / len(all_confs) if all_confs else 0.0
    return OcrPage(blocks, round(mean_conf, 2), psm, len(words), gutter)


def _score(p: OcrPage) -> float:
    """Rank OCR attempts. Confidence alone is gameable -- a pass that recognises
    three words at 95% is worse than one that recognises 400 at 80%."""
    if p.n_words == 0:
        return 0.0
    coverage = min(1.0, p.n_words / 250.0)
    return (p.mean_confidence / 100.0) * (0.35 + 0.65 * coverage)


def ocr_page(page: "fitz.Page", page_no: int, dpi: int = 300,
             lang: str = "eng", allow_retry: bool = True) -> Tuple[OcrPage, List[str]]:
    """OCR one page, retrying with alternate segmentation if the first pass is weak."""
    warnings: List[str] = []
    img = render_page(page, dpi=dpi)
    scale = 72.0 / float(dpi)  # pixels -> PDF points

    rot = detect_rotation(img)
    if rot:
        img = img.rotate(-rot, expand=True)
        warnings.append(f"page {page_no}: detected {rot}° rotation, corrected before OCR")

    page_width = float(page.rect.width)
    best = _ocr_once(img, page_no, scale, page_width, _PSM_PRIMARY, lang)
    if allow_retry and (best.mean_confidence < _RETRY_CONF_FLOOR
                        or best.n_words < _RETRY_WORD_FLOOR):
        for psm in _PSM_RETRIES:
            cand = _ocr_once(img, page_no, scale, page_width, psm, lang)
            if _score(cand) > _score(best):
                warnings.append(
                    f"page {page_no}: psm{_PSM_PRIMARY} weak "
                    f"(conf {best.mean_confidence:.0f}, {best.n_words}w) — "
                    f"psm{psm} used instead (conf {cand.mean_confidence:.0f}, {cand.n_words}w)"
                )
                best = cand
    return best, warnings
