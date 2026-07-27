"""Split a resume into canonical sections.

Why this belongs in the extractor rather than the ranker: the evidence needed to
find section headers -- font size, boldness, block geometry -- exists here and
is gone by the time you have a flat string. Recovering sections from plain text
afterwards is strictly harder than capturing them during extraction.

Downstream this is load-bearing for scoring. "Kubernetes" appearing in a skills
laundry list is weak evidence; "Kubernetes" inside an experience bullet with
dates around it is strong evidence. A ranker that cannot tell the two apart
rewards keyword stuffing.
"""

from __future__ import annotations

import re
import statistics
from typing import Dict, List, Sequence

from .types import Block

HEADER = "header"          # name / contact block above the first real section
OTHER = "other"

_ALIASES: Dict[str, Sequence[str]] = {
    "summary": ("summary", "professional summary", "profile", "objective",
                "career objective", "about me", "about", "professional profile"),
    "experience": ("experience", "work experience", "professional experience",
                   "employment", "employment history", "work history", "career history",
                   "relevant experience", "industry experience", "internships",
                   "internship", "internship experience", "positions"),
    "education": ("education", "academic background", "academics", "qualifications",
                  "educational qualifications", "academic qualifications"),
    "skills": ("skills", "technical skills", "core skills", "key skills",
               "skills summary", "technical proficiencies", "competencies",
               "core competencies", "technologies", "tech stack", "expertise",
               "areas of expertise", "tools", "tools and technologies"),
    "projects": ("projects", "personal projects", "key projects", "selected projects",
                 "academic projects", "project experience", "portfolio"),
    "certifications": ("certifications", "certification", "certificates",
                       "licenses", "licenses and certifications", "courses",
                       "training", "professional development"),
    "awards": ("awards", "honors", "honours", "achievements", "accomplishments",
               "awards and honors", "recognition"),
    "publications": ("publications", "papers", "research", "patents",
                     "research experience", "conference presentations"),
    "languages": ("languages", "language proficiency"),
    "interests": ("interests", "hobbies", "activities", "extracurricular",
                  "extracurricular activities", "volunteering", "volunteer experience",
                  "community involvement"),
    "contact": ("contact", "contact information", "personal details",
                "personal information", "details"),
}

_LOOKUP: Dict[str, str] = {}
for _canon, _names in _ALIASES.items():
    for _n in _names:
        _LOOKUP[_n] = _canon

_NORM_RE = re.compile(r"[^a-z& ]+")
_MAX_HEADER_WORDS = 5
_MAX_HEADER_CHARS = 48


def _normalise(line: str) -> str:
    s = _NORM_RE.sub(" ", line.lower())
    return re.sub(r"\s+", " ", s).strip()


def is_header_line(line: str, *, font_size: float | None = None,
                   median_size: float | None = None, bold: bool = False) -> str | None:
    """Return the canonical section name if `line` reads as a section header.

    Two conditions must both hold: the text must match a known section name,
    and the line must *look* like a heading. Requiring both stops "skills" in
    the sentence "transferred my skills to a new team" from opening a section.
    """
    raw = line.strip()
    if not raw or len(raw) > _MAX_HEADER_CHARS:
        return None
    if len(raw.split()) > _MAX_HEADER_WORDS:
        return None

    canon = _LOOKUP.get(_normalise(raw))
    if canon is None:
        return None

    looks_like_heading = (
        raw.isupper()
        or bold
        or raw.rstrip(":").istitle()
        or raw.endswith(":")
        or (font_size is not None and median_size is not None
            and font_size >= median_size * 1.12)
    )
    return canon if looks_like_heading else None


def assign_sections(blocks: List[Block]) -> Dict[str, str]:
    """Tag each block with its section and return {section: text}.

    Blocks are tagged in place so per-block section provenance survives into the
    JSON output -- a ranker can then ask "which section did this skill come
    from?" without re-parsing anything.
    """
    if not blocks:
        return {}

    sizes = [b.font_size for b in blocks if b.font_size]
    median_size = statistics.median(sizes) if sizes else None

    current = HEADER
    out: Dict[str, List[str]] = {}

    for b in blocks:
        lines = b.text.splitlines() or [b.text]
        first = lines[0] if lines else ""

        canon = is_header_line(
            first, font_size=b.font_size, median_size=median_size, bold=b.bold
        )
        if canon:
            current = canon
            b.section = canon
            body = "\n".join(lines[1:]).strip()   # header and body share a block
            if body:
                out.setdefault(current, []).append(body)
            continue

        b.section = current
        if b.text.strip():
            out.setdefault(current, []).append(b.text.strip())

    return {k: "\n".join(v).strip() for k, v in out.items() if "".join(v).strip()}
