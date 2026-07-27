"""Scoring — turn the LLM's depth judgements into an explainable 0-100.

This is the step the whole architecture was arranged around. Because the model
already did the judging (each skill has a depth: none / mentioned / used /
strong), the number is now plain arithmetic that a human can read line by line.
That is the entire point of keeping the LLM on the evidence side: "why 73?" is
answerable here, deterministically, and the same inputs always give the same 73.

The formula, in words:

    score = mandatory_bucket + preferred_bucket

    each bucket = weight × (Σ depth_weight of its skills ÷ number of its skills)

with depth_weight = none 0.0, mentioned 0.4, used 0.8, strong 1.0. A required
skill only *listed* (mentioned) earns 40% of its share, not full credit — which
is how keyword-stuffing is denied its payoff. Mandatory skills sit in the larger
bucket, so a missing must-have costs far more than a missing nice-to-have.

Two things deliberately do NOT move the number:
  * extraction confidence (from stage 1) — a resume that barely OCR'd is a
    *document* problem, not a candidate problem, so it flags for review rather
    than silently lowering the score;
  * LLM self-confidence — surfaced as a flag when low, but the score comes from
    the depth label, not the model's feeling about it, to keep it reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from Parser.schema import (CandidateScore, Depth, DEPTH_WEIGHT, Importance,
                           Requirements, ScoreComponent, SkillAssessment)


@dataclass
class ScoringConfig:
    w_mandatory: float = 70.0     # points available from required skills
    w_preferred: float = 30.0     # points available from preferred skills
    low_extraction_conf: float = 0.6   # below this -> flag for review
    low_llm_conf: float = 0.45         # per-skill; below this -> note
    demonstrated = (Depth.USED, Depth.STRONG)   # counts as "actually shown"


def _bucket(assessments: List[SkillAssessment], weight: float
            ) -> tuple[float, float, str]:
    """Return (earned, possible, detail) for one importance bucket."""
    if not assessments:
        return 0.0, 0.0, "no skills in this bucket"
    per_skill = weight / len(assessments)
    earned = sum(DEPTH_WEIGHT[a.depth] * per_skill for a in assessments)
    shown = sum(1 for a in assessments if a.depth in (Depth.USED, Depth.STRONG))
    listed = sum(1 for a in assessments if a.depth == Depth.MENTIONED)
    missing = sum(1 for a in assessments if a.depth == Depth.NONE)
    detail = (f"{shown} demonstrated, {listed} listed-only, {missing} missing "
              f"of {len(assessments)}")
    return round(earned, 2), round(weight, 2), detail


def score_candidate(requirements: Requirements,
                    assessments: List[SkillAssessment],
                    path: str = "",
                    extraction_confidence: float = 1.0,
                    config: Optional[ScoringConfig] = None) -> CandidateScore:
    """Compute an explainable CandidateScore for one resume."""
    cfg = config or ScoringConfig()

    mand = [a for a in assessments if a.importance == Importance.MANDATORY]
    pref = [a for a in assessments if a.importance == Importance.PREFERRED]

    # If the JD has no preferred skills, its weight folds into mandatory so the
    # scale stays 0-100 rather than topping out at 70.
    w_mand, w_pref = cfg.w_mandatory, cfg.w_preferred
    if not pref and mand:
        w_mand += w_pref
        w_pref = 0.0
    elif not mand and pref:
        w_pref += w_mand
        w_mand = 0.0

    m_earned, m_poss, m_detail = _bucket(mand, w_mand)
    p_earned, p_poss, p_detail = _bucket(pref, w_pref)

    components = [
        ScoreComponent("Mandatory skills", m_earned, m_poss, m_detail),
        ScoreComponent("Preferred skills", p_earned, p_poss, p_detail),
    ]
    score = round(m_earned + p_earned, 1)

    # matched vs missing/weak, in the language the brief asks for.
    matched = [a.skill for a in assessments if a.depth != Depth.NONE]
    missing_or_weak = (
        [f"{a.skill} (missing)" for a in assessments if a.depth == Depth.NONE]
        + [f"{a.skill} (listed only, not demonstrated)"
           for a in mand if a.depth == Depth.MENTIONED]
    )

    flags: List[str] = []
    missing_mand = [a.skill for a in mand if a.depth == Depth.NONE]
    if missing_mand:
        flags.append("missing required skill(s): " + ", ".join(missing_mand))
    if extraction_confidence < cfg.low_extraction_conf:
        flags.append(f"low extraction confidence ({extraction_confidence:.2f}) "
                     f"— recommend manual review of the source resume")
    low_conf = [a.skill for a in assessments
                if a.llm_confidence is not None and a.llm_confidence < cfg.low_llm_conf
                and a.depth != Depth.NONE]
    if low_conf:
        flags.append("low-confidence judgement(s): " + ", ".join(low_conf))

    return CandidateScore(
        path=path, score=score, summary=_summarise(requirements, mand, pref, score),
        matched_skills=matched, missing_or_weak=missing_or_weak,
        components=components, assessments=assessments,
        extraction_confidence=extraction_confidence, flags=flags,
    )


def _summarise(req: Requirements, mand: List[SkillAssessment],
               pref: List[SkillAssessment], score: float) -> str:
    """Deterministic one-line summary — no extra LLM call, fully reproducible.

    Templated rather than model-generated on purpose: the summary must never
    disagree with the number beside it, and a generated sentence can drift from
    the arithmetic. An LLM 'polish' pass is an easy later add if desired.
    """
    shown = sum(1 for a in mand if a.depth in (Depth.USED, Depth.STRONG))
    strong = sum(1 for a in mand if a.depth == Depth.STRONG)
    p_shown = sum(1 for a in pref if a.depth in (Depth.USED, Depth.STRONG))

    verdict = ("Strong match" if score >= 75 else
               "Moderate match" if score >= 55 else
               "Weak match" if score >= 30 else "Poor match")
    role = f" for {req.role_title}" if req.role_title else ""
    parts = [f"{verdict}{role}."]
    if mand:
        parts.append(f"{shown}/{len(mand)} required skills demonstrated"
                     + (f" ({strong} strongly)" if strong else "") + ".")
    if pref:
        parts.append(f"{p_shown}/{len(pref)} preferred demonstrated.")
    missing = [a.skill for a in mand if a.depth == Depth.NONE]
    if missing:
        parts.append("Missing: " + ", ".join(missing) + ".")
    return " ".join(parts)
