"""Ranking — order candidates and mark where the order is uncertain.

Scoring is deterministic, so the numbers are directly comparable within one JD
run (same rubric, same job). Ranking therefore sorts by score, but adds two
things a bare sort misses:

  * **Deterministic tie-breaks.** Equal scores are broken by required-skill
    strength, then by how many skills were shown strongly, then by extraction
    confidence — so a re-run never reshuffles ties arbitrarily.
  * **Calibration flags.** Where two adjacent candidates are within a small
    margin, the ranking says so rather than implying a confident ordering. The
    honest signal is "these two are effectively tied", not a spurious 4-vs-5.

There is no cross-candidate LLM call and no global re-scoring: the score already
means the same thing for everyone, so calibration here is about *communicating*
uncertainty, not manufacturing separation.
"""

from __future__ import annotations

from typing import List

from Parser.schema import CandidateScore, Depth


def _tiebreak_key(c: CandidateScore):
    strong = sum(1 for a in c.assessments if a.depth == Depth.STRONG)
    used = sum(1 for a in c.assessments if a.depth in (Depth.USED, Depth.STRONG))
    # higher is better on every term; negate for ascending sort composition
    return (c.score, used, strong, c.extraction_confidence)


def rank_candidates(scores: List[CandidateScore],
                    tie_margin: float = 2.0) -> List[CandidateScore]:
    """Sort best-to-worst, assign ranks, and flag near-ties. Mutates in place
    (sets .rank) and returns the ordered list."""
    ordered = sorted(scores, key=_tiebreak_key, reverse=True)

    for i, c in enumerate(ordered):
        c.rank = i + 1

    # Flag adjacent candidates separated by less than the margin — their
    # relative order is within the noise of the depth judgements above them.
    for i in range(1, len(ordered)):
        gap = ordered[i - 1].score - ordered[i].score
        if gap < tie_margin:
            note = (f"within {tie_margin:.0f} pts of #{ordered[i-1].rank} "
                    f"({ordered[i-1].score:.0f}) — order is close, review both")
            if note not in ordered[i].flags:
                ordered[i].flags.append(note)
    return ordered


def rank_report(scores: List[CandidateScore]) -> List[dict]:
    """Compact ranked view for JSON output or a table."""
    ranked = rank_candidates(scores)
    return [{
        "rank": c.rank, "score": c.score, "candidate": c.role_or_path(),
        "summary": c.summary, "flags": c.flags,
    } for c in ranked]
