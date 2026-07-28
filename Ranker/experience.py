"""Experience estimation — how many years has this candidate actually worked?

The JD parser already extracts `min_years_experience`, and until now nothing
consumed it: a job asking for five years scored a new graduate exactly the same
as a ten-year veteran, provided their skill lists matched. This closes that.

Design: **no LLM call.** Date ranges in a resume are a bounded, regular parsing
problem, and stage 1 already tagged which blocks are the experience section. A
deterministic parser is cheaper (zero marginal tokens), reproducible, and — the
part that matters for this system — explainable down to the individual range:
"2021-2024 at Acme plus 2018-2021 at Beta, overlap merged, 6.0 years". A model
asked "how many years is this?" gives you a number you cannot audit.

Three things the naive version gets wrong, handled here:

* **Overlapping roles.** A contractor holding two concurrent positions, or a
  promotion listed as two entries at the same employer, must not have their
  time counted twice. Ranges are merged as intervals before summing.
* **"Present".** Open-ended ranges need a reference date. That date is a
  parameter, not `date.today()` called internally, because scoring elsewhere in
  this system is deterministic and a function whose output changes overnight
  would quietly break that guarantee.
* **Unparseable resumes.** A resume with no dates at all yields `None`, not
  zero. Zero is a claim ("this person has no experience"); `None` is the truth
  ("we could not tell"). The scorer treats them very differently — see
  `scoring.py`, where an unknown redistributes its weight and raises a flag
  rather than silently zeroing the candidate.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from Parser.schema import DateRange, ExperienceEstimate

# Sections whose dates describe employment. "education" is excluded on purpose:
# a four-year degree is not four years of professional experience, and counting
# it is the single most common way these systems overstate juniors.
EXPERIENCE_SECTIONS = ("experience", "projects")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
_SEP_RE = r"\s*(?:-|–|—|~|to|until|through)\s*"
_PRESENT_RE = r"(?:present|current(?:ly)?|now|ongoing|to\s*date|date)"
_YEAR_RE = r"(19[7-9]\d|20[0-4]\d)"

# "Jan 2021 - Mar 2024" | "2021 - 2024" | "01/2021 - Present" | "2021-Present"
_RANGE = re.compile(
    rf"(?P<s_month>{_MONTH_RE}|\d{{1,2}})?[\s./,-]*(?P<s_year>{_YEAR_RE})"
    rf"{_SEP_RE}"
    rf"(?:(?P<present>{_PRESENT_RE})"
    rf"|(?:(?P<e_month>{_MONTH_RE}|\d{{1,2}})?[\s./,-]*(?P<e_year>{_YEAR_RE})))",
    re.IGNORECASE,
)

# Fallback only: "5+ years of experience", "over 7 years"
_CLAIM = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b(?![^.]*\bold\b)",
    re.IGNORECASE,
)


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _parse_month(token: Optional[str]) -> Optional[int]:
    if not token:
        return None
    token = token.strip().lower()
    if token.isdigit():
        m = int(token)
        return m if 1 <= m <= 12 else None
    for name, num in _MONTHS.items():
        if token.startswith(name):
            return num
    return None


def _merge(ranges: List[DateRange]) -> int:
    """Total months covered by the union of the ranges.

    Concurrent roles and promotion-splits at one employer overlap; summing them
    naively inflates a three-year career into five. Interval union is the fix.
    """
    if not ranges:
        return 0
    spans = sorted(((r.start_month, r.end_month) for r in ranges))
    total, cur_start, cur_end = 0, *spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:                 # overlapping or adjacent
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    return total + (cur_end - cur_start)


def find_ranges(text: str, today: Optional[date] = None) -> List[DateRange]:
    """Extract every employment date range from a block of text."""
    today = today or date.today()
    now_idx = _month_index(today.year, today.month)
    out: List[DateRange] = []

    for m in _RANGE.finditer(text):
        s_year = int(m.group("s_year"))
        s_month = _parse_month(m.group("s_month")) or 1
        start = _month_index(s_year, s_month)

        if m.group("present"):
            end, is_current = now_idx, True
        else:
            e_year = int(m.group("e_year"))
            # An end month absent means "through that year"; December is the
            # honest reading of "2021 - 2024" for someone who left in 2024.
            e_month = _parse_month(m.group("e_month")) or 12
            end, is_current = _month_index(e_year, e_month), False

        if end < start:
            continue                          # reversed or misparsed; drop it
        if end > now_idx + 1:
            continue                          # future dates are not experience
        out.append(DateRange(start, end, is_current, m.group(0).strip()))

    return out


def estimate_experience(sections: Dict[str, str],
                        today: Optional[date] = None,
                        sections_to_scan: Tuple[str, ...] = EXPERIENCE_SECTIONS
                        ) -> ExperienceEstimate:
    """Estimate years of professional experience from a parsed resume.

    Returns an estimate whose `years` is None when the resume gives us nothing
    to work with — the caller must distinguish that from zero.
    """
    est = ExperienceEstimate()

    scanned = "\n".join(sections.get(name, "") for name in sections_to_scan)
    ranges = find_ranges(scanned, today=today)

    # Self-reported claims, from anywhere in the resume — used as a cross-check
    # against the computed figure, and as a fallback when there are no dates.
    whole = "\n".join(sections.values())
    claims = [float(c) for c in _CLAIM.findall(whole)]
    if claims:
        est.claimed_years = max(claims)

    if ranges:
        est.ranges = ranges
        months = _merge(ranges)
        est.years = round(months / 12.0, 1)
        est.method = "date-ranges"
        est.evidence = [r.raw for r in ranges][:6]

        if est.claimed_years is not None and est.claimed_years - est.years >= 2.0:
            est.warnings.append(
                f"resume claims {est.claimed_years:g} years but dated roles "
                f"total {est.years:g} — verify manually"
            )
    elif est.claimed_years is not None:
        # Unverified: no dates to check it against. Recorded, but the method is
        # flagged so the scorer can treat it as weaker evidence.
        est.years = est.claimed_years
        est.method = "claimed"
        est.warnings.append(
            f"no dated roles found — using the resume's own claim of "
            f"{est.claimed_years:g} years, which is unverified"
        )
    else:
        est.warnings.append(
            "no dates or stated experience found — years could not be determined"
        )

    if est.years is not None and est.years > 50:
        est.warnings.append(f"implausible total ({est.years:g} years) — "
                            f"likely a misparsed date")

    return est