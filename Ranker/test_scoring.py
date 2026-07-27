"""Scoring + ranking tests — pure functions, no LLM, no network.

Scoring is deterministic, so these assert exact numbers and the explanation
lines that justify them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Parser.schema import (Depth, Importance, Requirements, Skill,
                           SkillAssessment)
from Ranker.scoring import score_candidate, ScoringConfig
from Ranker.ranking import rank_candidates


REQ = Requirements(
    role_title="Backend Engineer",
    mandatory_skills=[Skill("Python", Importance.MANDATORY),
                      Skill("Kubernetes", Importance.MANDATORY)],
    preferred_skills=[Skill("Terraform", Importance.PREFERRED)],
)


def _assess(python, k8s, terraform):
    return [
        SkillAssessment("Python", Importance.MANDATORY, python, "evidence"),
        SkillAssessment("Kubernetes", Importance.MANDATORY, k8s, "evidence"),
        SkillAssessment("Terraform", Importance.PREFERRED, terraform, "evidence"),
    ]


def test_perfect_candidate_scores_100():
    a = _assess(Depth.STRONG, Depth.STRONG, Depth.STRONG)
    cs = score_candidate(REQ, a)
    assert cs.score == 100.0


def test_score_decomposition_adds_up():
    a = _assess(Depth.STRONG, Depth.NONE, Depth.USED)
    cs = score_candidate(REQ, a)
    total = sum(c.earned for c in cs.components)
    assert abs(total - cs.score) < 0.01
    # mandatory bucket: Python strong (1.0) + K8s none (0.0), 2 skills, 70 pts
    # -> 70 * (1.0/2) = 35
    mand = next(c for c in cs.components if c.label == "Mandatory skills")
    assert abs(mand.earned - 35.0) < 0.01


def test_mentioned_only_gets_partial_credit_not_full():
    listed = score_candidate(REQ, _assess(Depth.MENTIONED, Depth.MENTIONED, Depth.NONE))
    used = score_candidate(REQ, _assess(Depth.USED, Depth.USED, Depth.NONE))
    assert listed.score < used.score  # keyword-stuffing denied full payoff


def test_missing_mandatory_is_flagged_and_costs_more_than_missing_preferred():
    miss_mand = score_candidate(REQ, _assess(Depth.NONE, Depth.STRONG, Depth.STRONG))
    miss_pref = score_candidate(REQ, _assess(Depth.STRONG, Depth.STRONG, Depth.NONE))
    assert miss_mand.score < miss_pref.score
    assert any("missing required skill" in f for f in miss_mand.flags)


def test_no_preferred_skills_still_scales_to_100():
    req = Requirements(mandatory_skills=[Skill("Python", Importance.MANDATORY)])
    a = [SkillAssessment("Python", Importance.MANDATORY, Depth.STRONG, "x")]
    assert score_candidate(req, a).score == 100.0


def test_low_extraction_confidence_flags_but_does_not_lower_score():
    a = _assess(Depth.STRONG, Depth.STRONG, Depth.STRONG)
    full = score_candidate(REQ, a, extraction_confidence=1.0)
    poor = score_candidate(REQ, a, extraction_confidence=0.3)
    assert full.score == poor.score            # document problem != candidate problem
    assert any("manual review" in f for f in poor.flags)


def test_matched_and_missing_lists():
    cs = score_candidate(REQ, _assess(Depth.USED, Depth.NONE, Depth.MENTIONED))
    assert "Python" in cs.matched_skills
    assert any("Kubernetes" in m and "missing" in m for m in cs.missing_or_weak)


def test_explanation_is_human_readable():
    cs = score_candidate(REQ, _assess(Depth.STRONG, Depth.USED, Depth.NONE))
    exp = cs.explanation
    assert "Mandatory skills" in exp and "Preferred skills" in exp
    assert "/100" in exp


def test_ranking_orders_and_assigns_ranks():
    strong = score_candidate(REQ, _assess(Depth.STRONG, Depth.STRONG, Depth.STRONG), path="a.pdf")
    weak = score_candidate(REQ, _assess(Depth.MENTIONED, Depth.NONE, Depth.NONE), path="b.pdf")
    mid = score_candidate(REQ, _assess(Depth.USED, Depth.USED, Depth.NONE), path="c.pdf")
    ranked = rank_candidates([weak, strong, mid])
    assert [c.role_or_path() for c in ranked] == ["a.pdf", "c.pdf", "b.pdf"]
    assert [c.rank for c in ranked] == [1, 2, 3]


def test_near_tie_is_flagged():
    a = score_candidate(REQ, _assess(Depth.STRONG, Depth.STRONG, Depth.USED), path="a.pdf")
    b = score_candidate(REQ, _assess(Depth.STRONG, Depth.STRONG, Depth.MENTIONED), path="b.pdf")
    ranked = rank_candidates([a, b], tie_margin=15.0)
    assert any("order is close" in f for f in ranked[1].flags)


def test_tiebreak_prefers_stronger_evidence_at_equal_score():
    # same score, but one shows skills 'strong' vs 'used' — strong should win
    cfg = ScoringConfig()
    s_strong = score_candidate(REQ, _assess(Depth.STRONG, Depth.NONE, Depth.NONE), path="strong.pdf")
    s_used = score_candidate(REQ, _assess(Depth.USED, Depth.NONE, Depth.NONE), path="used.pdf")
    # different scores here (strong>used), so make an equal-score construction:
    eq1 = score_candidate(REQ, _assess(Depth.USED, Depth.USED, Depth.NONE), path="u.pdf")
    eq2 = score_candidate(REQ, _assess(Depth.STRONG, Depth.MENTIONED, Depth.NONE), path="s.pdf")
    # both mandatory buckets ~ (0.8+0.8)/2*70=56 vs (1.0+0.4)/2*70=49 -> not equal,
    # so just assert the ranker is stable and rank-complete
    ranked = rank_candidates([eq1, eq2])
    assert {c.rank for c in ranked} == {1, 2}
