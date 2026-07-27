"""Column detection and reading-order reconstruction.

The failure this module exists to prevent:

    Python, SQL, Docker      Senior Engineer, Acme Corp   2021-2023

That single line is what naive extraction produces from a two-column resume --
a sidebar skill list and an unrelated job title fused because they share a
y-coordinate. It does not crash, it does not warn, and it looks fine in a log.
Downstream, an embedding model happily encodes the nonsense.

Approach: find the vertical whitespace gutter from block geometry, assign each
block to a column, then emit column-major within horizontal bands. Bands matter
because almost every two-column resume has a full-width header (and often
full-width section rules) that must not be swallowed into one column.

Works identically on PyMuPDF blocks and tesseract blocks, so the native and OCR
paths share one ordering implementation.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .models import Block, Column

# A block wider than this fraction of the page cannot *be* a column: in a
# two-column layout each column occupies at most ~48% of the width. So anything
# above this is header/rule/full-width prose, and it must be excluded from
# gutter detection -- it bridges the gutter and hides it.
#
# This threshold is load-bearing. At 0.72 a typical contact line
# ("email | phone | linkedin | city", ~67% of width) survives the filter and
# flattens the whitespace profile to nothing, so no gutter is ever found.
_FULLWIDTH_FRAC = 0.60
# Minimum gutter width, as a fraction of page width and an absolute floor in pt.
_MIN_GUTTER_FRAC = 0.030
_MIN_GUTTER_PT = 12.0
# Ignore candidate gutters in the outer margins.
_MARGIN_FRAC = 0.15
# A single unusually wide token -- a long email address, a URL, a centred name
# -- is enough to bridge a real gutter and hide it. Such tokens are header
# furniture, not column content, so they are excluded from the ink profile.
# Relative to the page's own typical token width, so it needs no absolute
# tuning and scales with font and page size.
_OUTLIER_WIDTH_MULT = 4.0
_OUTLIER_WIDTH_FLOOR = 0.15
# Each side of a real two-column layout must span at least this share of the
# page's vertical content extent. Vertical *coverage*, not ink volume: a skills
# sidebar legitimately carries under 10% of a resume's words while running the
# full height of the page. An ink-share test rejects it as noise.
_MIN_SIDE_SHARE = 0.25


def _occupancy(blocks: Sequence[Block], page_width: float, bin_pt: float = 2.0
               ) -> Tuple[List[float], float]:
    """Horizontal ink profile: for each x-bin, total block height covering it.

    Weighting by height rather than block count keeps a one-line sidebar heading
    from looking as substantial as a 40-line experience column.
    """
    n_bins = max(1, int(math.ceil(page_width / bin_pt)))
    occ = [0.0] * n_bins

    widths = sorted(b.bbox[2] - b.bbox[0] for b in blocks)
    median_w = widths[len(widths) // 2] if widths else 0.0
    cutoff = min(
        _FULLWIDTH_FRAC * page_width,
        max(_OUTLIER_WIDTH_MULT * median_w, _OUTLIER_WIDTH_FLOOR * page_width),
    )

    for b in blocks:
        x0, y0, x1, y1 = b.bbox
        if (x1 - x0) > cutoff:
            continue  # spans/bridges the layout: tells us nothing about columns
        i0 = max(0, int(x0 / bin_pt))
        i1 = min(n_bins - 1, int(x1 / bin_pt))
        h = max(1.0, y1 - y0)
        for i in range(i0, i1 + 1):
            occ[i] += h
    return occ, bin_pt


def detect_gutter(blocks: Sequence[Block], page_width: float
                  ) -> Optional[Tuple[float, float]]:
    """Return (x_start, x_end) of the dominant vertical gutter, or None."""
    if len(blocks) < 4 or page_width <= 0:
        return None

    occ, bin_pt = _occupancy(blocks, page_width)
    total_ink = sum(occ)
    if total_ink <= 0:
        return None

    # Search inside the *content* extent, not the page extent. Page-relative
    # margins let the right-hand page margin masquerade as a candidate gutter
    # -- and it is usually wider than the real one, so a "widest run wins" rule
    # picks the margin every time and reports a single-column page.
    occupied = [i for i, v in enumerate(occ) if v > 0]
    c0, c1 = occupied[0], occupied[-1]
    span = c1 - c0
    if span <= 0:
        return None
    lo = c0 + int(_MARGIN_FRAC * span)
    hi = c1 - int(_MARGIN_FRAC * span)

    # Collect *every* empty run, then validate each. Keeping only the widest
    # discards the real gutter whenever some other gap happens to be wider.
    runs: List[Tuple[int, int]] = []
    run_start: Optional[int] = None
    for i in range(lo, hi + 1):
        if occ[i] == 0.0:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            runs.append((run_start, i))
            run_start = None
    if run_start is not None:
        runs.append((run_start, hi + 1))

    min_w = max(_MIN_GUTTER_PT, _MIN_GUTTER_FRAC * page_width)
    best: Optional[Tuple[float, Tuple[float, float]]] = None

    body = [b for b in blocks
            if (b.bbox[2] - b.bbox[0]) <= _FULLWIDTH_FRAC * page_width]
    if not body:
        return None
    total_span = max(b.bbox[3] for b in body) - min(b.bbox[1] for b in body)
    if total_span <= 0:
        return None

    for a, b in runs:
        x0, x1 = a * bin_pt, b * bin_pt
        if (x1 - x0) < min_w:
            continue
        left = [k for k in body if k.bbox[2] <= x0 + 1.0]
        right = [k for k in body if k.bbox[0] >= x1 - 1.0]
        if len(left) < 2 or len(right) < 2:
            continue
        # A real column runs down the page. A spurious gap -- the space before
        # a right-aligned date, say -- has content on only a line or two.
        l_span = max(k.bbox[3] for k in left) - min(k.bbox[1] for k in left)
        r_span = max(k.bbox[3] for k in right) - min(k.bbox[1] for k in right)
        balance = min(l_span, r_span) / total_span
        if balance < _MIN_SIDE_SHARE:
            continue
        score = balance + 0.001 * (x1 - x0)
        if best is None or score > best[0]:
            best = (score, (x0, x1))

    return best[1] if best else None


def _classify(b: Block, gutter: Tuple[float, float], page_width: float) -> int:
    """Assign a block to a column.

    The rule is overlap, not centroid: the gutter is by construction empty of
    column content, so any block intruding into it cannot belong to a single
    column and is treated as full-width. Centroid tests get this wrong for
    centred headers, which sit mostly on one side and would be silently
    absorbed into that column.
    """
    gs, ge = gutter
    x0, _, x1, _ = b.bbox
    if (x1 - x0) > _FULLWIDTH_FRAC * page_width:
        return Column.FULL
    if x0 < ge - 1.0 and x1 > gs + 1.0:   # intrudes into the gutter
        return Column.FULL
    return Column.LEFT if x1 <= gs + 1.0 else Column.RIGHT


def _refine_gutter(blocks: Sequence[Block], gutter: Tuple[float, float],
                   page_width: float) -> Tuple[float, float]:
    """Widen the gutter to the true whitespace band between the columns.

    Detection finds *a* clear strip, but a straddling header can clip it short.
    Once blocks are provisionally classified, the real boundary is simply the
    rightmost edge of the left column and the leftmost edge of the right one.
    Reclassifying against the widened band then catches straddlers that the
    initial narrow estimate missed.
    """
    left = [b.bbox[2] for b in blocks if _classify(b, gutter, page_width) == Column.LEFT]
    right = [b.bbox[0] for b in blocks if _classify(b, gutter, page_width) == Column.RIGHT]
    if not left or not right:
        return gutter
    gs, ge = max(left), min(right)
    return (gs, ge) if ge - gs >= 1.0 else gutter


def order_blocks(blocks: List[Block], page_width: float,
                 gutter: Optional[Tuple[float, float]] = None
                 ) -> Tuple[List[Block], int, Optional[Tuple[float, float]]]:
    """Reconstruct reading order. Returns (ordered blocks, n_columns, gutter).

    `gutter` may be supplied by a caller that already detected columns at a
    finer granularity. The OCR path does exactly this: it detects on individual
    word boxes, which is the most reliable input available, because a word box
    never straddles a gutter. Re-detecting afterwards on grouped lines is
    strictly worse information and lets the pipeline disagree with itself about
    how many columns a page has.
    """
    if not blocks:
        return [], 0, None

    if gutter is None:
        gutter = detect_gutter(blocks, page_width)

    if gutter is None:
        ordered = sorted(blocks, key=lambda b: (round(b.bbox[1], 1), b.bbox[0]))
        for i, b in enumerate(ordered):
            b.column = Column.FULL
            b.order = i
        return ordered, 1, None

    gutter = _refine_gutter(blocks, gutter, page_width)
    for b in blocks:
        b.column = _classify(b, gutter, page_width)

    # Split into horizontal bands at every full-width block, then read each band
    # column-major: all of the left column, then all of the right.
    by_y = sorted(blocks, key=lambda b: (round(b.bbox[1], 1), b.bbox[0]))
    ordered: List[Block] = []
    band: List[Block] = []

    def flush() -> None:
        if not band:
            return
        left = sorted((b for b in band if b.column == Column.LEFT),
                      key=lambda b: (b.bbox[1], b.bbox[0]))
        right = sorted((b for b in band if b.column == Column.RIGHT),
                       key=lambda b: (b.bbox[1], b.bbox[0]))
        ordered.extend(left)
        ordered.extend(right)
        band.clear()

    for b in by_y:
        if b.column == Column.FULL:
            flush()
            ordered.append(b)
        else:
            band.append(b)
    flush()

    for i, b in enumerate(ordered):
        b.order = i
    return ordered, 2, gutter


def merge_paragraphs(blocks: List[Block], line_gap_factor: float = 1.9) -> List[Block]:
    """Merge consecutive blocks that are really one paragraph.

    Extractors emit blocks at whatever granularity the producing application
    used -- often one per rendered line. Line-granular blocks are poor units for
    downstream chunking and embedding: "Built a streaming ingestion platform
    handling 2M events" and its continuation line embed as two half-thoughts.

    Merging stops at section headers, so each section still begins a new block
    and section assignment keeps working.
    """
    if not blocks:
        return blocks

    from .sections import is_header_line  # local import avoids a cycle

    heights = [b.bbox[3] - b.bbox[1] for b in blocks if b.bbox[3] > b.bbox[1]]
    med_h = sorted(heights)[len(heights) // 2] if heights else 12.0
    max_gap = med_h * line_gap_factor

    out: List[Block] = [blocks[0]]
    for b in blocks[1:]:
        prev = out[-1]
        gap = b.bbox[1] - prev.bbox[3]
        same_col = (b.column == prev.column) and (b.page == prev.page)
        aligned = abs(b.bbox[0] - prev.bbox[0]) <= 14.0
        similar_size = (
            b.font_size is None or prev.font_size is None
            or abs(b.font_size - prev.font_size) <= 0.15 * max(b.font_size, prev.font_size)
        )
        starts_section = is_header_line(
            b.text.splitlines()[0] if b.text else "", bold=b.bold
        ) is not None
        same_table = b.in_table == prev.in_table

        if (same_col and aligned and similar_size and same_table
                and not starts_section and 0 <= gap <= max_gap):
            prev.text = f"{prev.text}\n{b.text}"
            prev.bbox = (min(prev.bbox[0], b.bbox[0]), prev.bbox[1],
                         max(prev.bbox[2], b.bbox[2]), b.bbox[3])
            if b.confidence is not None and prev.confidence is not None:
                prev.confidence = round((prev.confidence + b.confidence) / 2, 2)
        else:
            out.append(b)

    for i, b in enumerate(out):
        b.order = i
    return out


def blocks_to_text(blocks: Sequence[Block]) -> str:
    """Join ordered blocks, preserving the blank lines that mark structure.

    The old pipeline dropped every empty line during "cleaning". Those blank
    lines are the strongest available signal for section boundaries -- deleting
    them destroys exactly the structure the section splitter needs to tell
    "Python" in a skills dump from "Python" in a job bullet.
    """
    parts = [b.text.strip() for b in blocks if b.text and b.text.strip()]
    return "\n\n".join(parts)
