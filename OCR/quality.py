"""Is this text actually any good?

This module exists to replace the single worst line in the old pipeline:

    if not text or len(text.strip()) < 50:  # ...then OCR

That heuristic fails open. A scanned resume exported from Canva or an ATS
carries a junk text layer -- a watermark, a page number, a broken embedded OCR
layer -- that clears 50 characters easily. OCR never fires and the candidate is
ranked on noise.

Instead we score the text on several independent signals and return an
*explainable* verdict: which signals fired, how much each cost, and what to do.
"""

from __future__ import annotations

import re
from typing import List

from .models import QualityReport, QualitySignal, Verdict

# Encoding-failure artefacts: unmapped CIDs, replacement chars, private-use
# glyphs. These appear when a font has no usable ToUnicode map -- the text layer
# "exists" but decodes to garbage.
_GARBAGE_RE = re.compile(r"\(cid:\d+\)|[\uFFFD\uE000-\uF8FF]")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*")
_VOWEL_RE = re.compile(r"[aeiouyAEIOUY]")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_URL_RE = re.compile(r"(?:https?://|www\.|linkedin\.com|github\.com)", re.I)

_SECTION_HINTS = (
    "experience", "education", "skills", "projects", "summary", "objective",
    "certification", "employment", "work history", "achievements", "profile",
    "internship", "publications", "languages", "awards", "contact",
)


def _pct(n: int, d: int) -> float:
    return (n / d) if d else 0.0


def assess(text: str, n_pages: int = 1, context: str = "") -> QualityReport:
    """Score extracted text 0-1 and classify it.

    `context` is a free-text label ("page 3 native") used only in signal notes,
    so a log line or a JSON report explains itself without extra plumbing.
    """
    signals: List[QualitySignal] = []
    stripped = text.strip()

    if not stripped:
        signals.append(QualitySignal("empty", 0.0, 1.0, "no characters extracted"))
        return QualityReport(0.0, Verdict.EMPTY, signals)

    chars = len(stripped)
    non_space = sum(1 for c in stripped if not c.isspace())
    words = _WORD_RE.findall(stripped)
    n_words = len(words)

    score = 1.0

    # --- 1. Density -------------------------------------------------------
    # A real resume page runs 1500-4000 chars. A page that yields 120 chars
    # either is scanned, or lost its content to a layout the parser can't read.
    per_page = chars / max(1, n_pages)
    if per_page < 120:
        p = 0.55
        note = f"very low text density ({per_page:.0f} chars/page) — likely scanned or image-only"
    elif per_page < 400:
        p = 0.25
        note = f"low text density ({per_page:.0f} chars/page) — partial extraction likely"
    else:
        p = 0.0
        note = f"text density normal ({per_page:.0f} chars/page)"
    score -= p
    signals.append(QualitySignal("density", round(per_page, 1), p, note))

    # --- 2. Encoding garbage ---------------------------------------------
    garbage = sum(len(m.group(0)) for m in _GARBAGE_RE.finditer(stripped))
    g_ratio = _pct(garbage, chars)
    p = min(0.6, g_ratio * 6.0)
    score -= p
    signals.append(QualitySignal(
        "encoding_garbage", round(g_ratio, 4), p,
        f"{g_ratio:.1%} of characters are CID/replacement artefacts — broken font encoding"
        if p else "no encoding artefacts",
    ))

    # --- 3. Alphabetic content -------------------------------------------
    # Dashes, dots and box-drawing from a mangled table dump score low here.
    alpha = sum(1 for c in stripped if c.isalpha())
    a_ratio = _pct(alpha, non_space)
    if a_ratio < 0.45:
        p = 0.35
        note = f"only {a_ratio:.0%} alphabetic — output looks like symbols/noise, not prose"
    elif a_ratio < 0.6:
        p = 0.12
        note = f"low alphabetic ratio ({a_ratio:.0%})"
    else:
        p = 0.0
        note = f"alphabetic ratio normal ({a_ratio:.0%})"
    score -= p
    signals.append(QualitySignal("alpha_ratio", round(a_ratio, 3), p, note))

    # --- 4. Character-spacing mangling ------------------------------------
    # Some PDF generators emit one glyph per text-run with explicit kerning.
    # Naive extraction yields "S O F T W A R E   E N G I N E E R". Length is
    # fine, density is fine -- but every token is a single letter.
    if n_words >= 20:
        singles = sum(1 for w in words if len(w) == 1)
        s_ratio = _pct(singles, n_words)
        if s_ratio > 0.4:
            p = 0.45
            note = f"{s_ratio:.0%} of tokens are single letters — character-spacing mangling"
        elif s_ratio > 0.25:
            p = 0.18
            note = f"{s_ratio:.0%} single-letter tokens — spacing may be mangled"
        else:
            p = 0.0
            note = "token lengths normal"
        score -= p
        signals.append(QualitySignal("single_char_tokens", round(s_ratio, 3), p, note))

    # --- 5. Word plausibility --------------------------------------------
    # OCR on a bad scan produces letter salad: tokens with no vowels, absurd
    # lengths. Cheap language-agnostic sanity check, no dictionary needed.
    if n_words >= 20:
        plausible = sum(1 for w in words if (len(w) <= 2 or _VOWEL_RE.search(w)) and len(w) <= 22)
        pl_ratio = _pct(plausible, n_words)
        if pl_ratio < 0.7:
            p = 0.4
            note = f"only {pl_ratio:.0%} of tokens look like real words — OCR noise or bad decode"
        elif pl_ratio < 0.85:
            p = 0.15
            note = f"{pl_ratio:.0%} plausible tokens — some noise present"
        else:
            p = 0.0
            note = f"{pl_ratio:.0%} of tokens are plausible words"
        score -= p
        signals.append(QualitySignal("word_plausibility", round(pl_ratio, 3), p, note))

    # --- 6. Resume-shaped? ------------------------------------------------
    # Domain check. Text can be clean English and still be the wrong text --
    # e.g. we extracted only a cover page or a footer template. Contact details
    # plus section headers are near-universal in resumes.
    low = stripped.lower()
    hits = sum(1 for h in _SECTION_HINTS if h in low)
    has_contact = bool(_EMAIL_RE.search(stripped) or _PHONE_RE.search(stripped)
                       or _URL_RE.search(stripped))
    if chars > 400 and hits == 0 and not has_contact:
        p = 0.2
        note = "no section headers or contact details found — may not be a resume, or extraction is partial"
    elif hits == 0 and not has_contact:
        p = 0.08
        note = "no resume landmarks found (short text — may be a fragment)"
    else:
        p = 0.0
        note = f"{hits} section landmark(s){', contact details present' if has_contact else ''}"
    score -= p
    signals.append(QualitySignal("resume_landmarks", float(hits), p, note))

    score = max(0.0, min(1.0, score))

    if score >= 0.75:
        verdict = Verdict.GOOD
    elif score >= 0.45:
        verdict = Verdict.SUSPECT
    else:
        verdict = Verdict.BAD

    if context:
        for s in signals:
            s.note = f"[{context}] {s.note}"

    return QualityReport(score, verdict, signals)


def better_of(a: QualityReport, b: QualityReport, margin: float = 0.05) -> bool:
    """True if `b` is meaningfully better than `a`.

    The margin stops us swapping a native text layer for an OCR pass that is
    only trivially better — native text is exact where OCR is probabilistic, so
    it wins ties.
    """
    return b.score > a.score + margin
