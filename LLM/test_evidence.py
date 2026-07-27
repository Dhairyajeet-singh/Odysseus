"""Evidence-extraction tests — offline, via MockProvider.

Assert the logic around the model: depth coercion, importance coming from the
JD (not the model), the grounding check catching a hallucinated quote, omitted
skills defaulting to 'none', and provider failure being contained.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Parser import (Depth, Importance, MockProvider, Requirements, Skill)
from Retriever import HashingEmbedder
from LLM.evidence import assess_resume
from Retriever.retriever import HybridRetriever

SECTIONS = {
    "skills": "Python, Kubernetes, PostgreSQL",
    "experience": (
        "Senior Engineer (2021-2024)\n\n"
        "Built data pipelines in Python processing 2M events per minute.\n\n"
        "Operated production services on Kubernetes across three regions."
    ),
}

REQ = Requirements(
    role_title="Backend Engineer",
    mandatory_skills=[Skill("Python", Importance.MANDATORY),
                      Skill("Kubernetes", Importance.MANDATORY)],
    preferred_skills=[Skill("Terraform", Importance.PREFERRED)],
)


def _evidence():
    r = HybridRetriever(SECTIONS, embedder=HashingEmbedder())
    return r.retrieve_all(REQ, top_k=3)


def good_router(system, user):
    return {"assessments": [
        {"skill": "Python", "depth": "strong",
         "evidence": "Built data pipelines in Python processing 2M events per minute",
         "section": "experience", "confidence": 0.9},
        {"skill": "Kubernetes", "depth": "used",
         "evidence": "Operated production services on Kubernetes across three regions",
         "section": "experience", "confidence": 0.85},
        {"skill": "Terraform", "depth": "none", "evidence": "", "confidence": 0.95},
    ]}


def test_depth_and_evidence_parsed():
    assessments, warns = assess_resume(REQ, _evidence(), MockProvider(good_router))
    by = {a.skill: a for a in assessments}
    assert by["Python"].depth == Depth.STRONG
    assert by["Kubernetes"].depth == Depth.USED
    assert by["Terraform"].depth == Depth.NONE
    assert not warns


def test_importance_comes_from_jd_not_model():
    """Even if the model tried to assert importance, we take it from the JD."""
    assessments, _ = assess_resume(REQ, _evidence(), MockProvider(good_router))
    by = {a.skill: a for a in assessments}
    assert by["Python"].importance == Importance.MANDATORY
    assert by["Terraform"].importance == Importance.PREFERRED


def test_hallucinated_evidence_is_flagged():
    """A quote that never appears in the resume must be caught and penalised."""
    def liar(system, user):
        return {"assessments": [
            {"skill": "Python", "depth": "strong",
             "evidence": "Led a 40-person AI research org at Google for nine years",
             "section": "experience", "confidence": 0.99},
            {"skill": "Kubernetes", "depth": "none", "evidence": "", "confidence": 0.9},
            {"skill": "Terraform", "depth": "none", "evidence": "", "confidence": 0.9},
        ]}
    assessments, warns = assess_resume(REQ, _evidence(), MockProvider(liar))
    py = next(a for a in assessments if a.skill == "Python")
    assert py.evidence.startswith("[unverified]")
    assert py.llm_confidence < 0.5
    assert any("ungrounded" in w for w in warns)


def test_omitted_skill_defaults_to_none():
    def forgets(system, user):
        return {"assessments": [
            {"skill": "Python", "depth": "used", "evidence":
             "Built data pipelines in Python", "confidence": 0.8}]}
    assessments, warns = assess_resume(REQ, _evidence(), MockProvider(forgets))
    skills = {a.skill for a in assessments}
    assert skills == {"Python", "Kubernetes", "Terraform"}  # none dropped
    k = next(a for a in assessments if a.skill == "Kubernetes")
    assert k.depth == Depth.NONE
    assert any("omitted" in w for w in warns)


def test_invalid_depth_coerced_to_none():
    def weird(system, user):
        return {"assessments": [
            {"skill": "Python", "depth": "expert-level-god", "evidence":
             "Built data pipelines in Python", "confidence": 0.8},
            {"skill": "Kubernetes", "depth": "none", "confidence": 0.9},
            {"skill": "Terraform", "depth": "none", "confidence": 0.9},
        ]}
    assessments, _ = assess_resume(REQ, _evidence(), MockProvider(weird))
    py = next(a for a in assessments if a.skill == "Python")
    assert py.depth == Depth.NONE


def test_provider_failure_contained():
    def boom(system, user):
        raise RuntimeError("429 rate limited")
    assessments, warns = assess_resume(REQ, _evidence(), MockProvider(boom))
    assert all(a.depth == Depth.NONE for a in assessments)
    assert any("failed" in w for w in warns)


def test_grounding_tolerates_minor_rewording():
    """A faithful near-quote should still count as grounded."""
    def reworded(system, user):
        return {"assessments": [
            {"skill": "Python", "depth": "strong",
             "evidence": "built data pipelines in python processing 2M events",
             "section": "experience", "confidence": 0.9},
            {"skill": "Kubernetes", "depth": "none", "confidence": 0.9},
            {"skill": "Terraform", "depth": "none", "confidence": 0.9},
        ]}
    assessments, warns = assess_resume(REQ, _evidence(), MockProvider(reworded))
    py = next(a for a in assessments if a.skill == "Python")
    assert not py.evidence.startswith("[unverified]")
    assert not any("ungrounded" in w for w in warns)
