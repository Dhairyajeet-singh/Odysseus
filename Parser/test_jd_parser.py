"""JD parser tests — no API key, no network, via MockProvider.

The mock returns what a real model would plausibly return for the sample JD, so
we can assert the deterministic layer around the model exactly: the
mandatory/preferred split, alias normalisation, and graceful handling of a
malformed response.
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resume_match import Importance, MockProvider, parse_jd

SAMPLE_JD = """
Senior Backend Engineer

We are looking for a senior engineer with 5+ years of experience to join our
platform team. You must have strong Python and PostgreSQL skills, and solid
experience with AWS. Experience with Kubernetes is a plus, and familiarity with
Kafka would be nice to have.

Responsibilities:
- Design and operate high-throughput services
- Mentor junior engineers

Bachelor's degree in Computer Science or equivalent.
"""


def good_router(system, user):
    """What a competent model returns for SAMPLE_JD."""
    return {
        "role_title": "Senior Backend Engineer",
        "mandatory_skills": [
            {"name": "Python", "category": "language"},
            {"name": "PostgreSQL", "category": "database"},
            {"name": "Amazon Web Services", "category": "cloud"},
        ],
        "preferred_skills": [
            {"name": "Kubernetes", "category": "infra"},
            {"name": "Kafka", "category": "infra"},
        ],
        "min_years_experience": 5,
        "education": "Bachelor's in Computer Science or equivalent",
        "responsibilities": [
            "Design and operate high-throughput services",
            "Mentor junior engineers",
        ],
    }


def test_parses_role_and_experience():
    req = parse_jd(SAMPLE_JD, MockProvider(good_router))
    assert req.role_title == "Senior Backend Engineer"
    assert req.min_years_experience == 5.0


def test_separates_mandatory_from_preferred():
    """The split that makes mandatory-vs-preferred weighting possible."""
    req = parse_jd(SAMPLE_JD, MockProvider(good_router))
    mandatory = {s.name for s in req.mandatory_skills}
    preferred = {s.name for s in req.preferred_skills}
    assert "Python" in mandatory and "PostgreSQL" in mandatory
    assert "Kubernetes" in preferred and "Kafka" in preferred
    assert mandatory.isdisjoint(preferred)


def test_aliases_attached_for_normalisation():
    """'AWS' in a resume must be able to match 'Amazon Web Services' here."""
    req = parse_jd(SAMPLE_JD, MockProvider(good_router))
    aws = next(s for s in req.mandatory_skills if s.name == "Amazon Web Services")
    assert "aws" in aws.aliases
    k8s = next(s for s in req.preferred_skills if s.name == "Kubernetes")
    assert "k8s" in k8s.aliases


def test_every_skill_carries_importance():
    req = parse_jd(SAMPLE_JD, MockProvider(good_router))
    assert all(s.importance == Importance.MANDATORY for s in req.mandatory_skills)
    assert all(s.importance == Importance.PREFERRED for s in req.preferred_skills)


def test_malformed_model_response_degrades_gracefully():
    """A junk entry is dropped with a warning, not a crash."""
    def messy_router(system, user):
        return {
            "role_title": "Data Scientist",
            "mandatory_skills": [{"name": "Python"}, {"category": "no name here"}, 42],
            "preferred_skills": "not even a list",
            "min_years_experience": "three",
        }

    req = parse_jd("some jd", MockProvider(messy_router))
    assert req.role_title == "Data Scientist"
    assert [s.name for s in req.mandatory_skills] == ["Python"]
    assert req.preferred_skills == []
    assert req.min_years_experience is None
    assert any("malformed" in w for w in req.warnings)
    assert any("min_years" in w for w in req.warnings)


def test_provider_failure_is_contained():
    """If the LLM call itself throws, we get a warning-bearing result."""
    def boom(system, user):
        raise RuntimeError("rate limited")

    req = parse_jd(SAMPLE_JD, MockProvider(boom))
    assert req.mandatory_skills == []
    assert any("JD parse failed" in w for w in req.warnings)


def test_empty_jd():
    req = parse_jd("   ", MockProvider(good_router))
    assert any("empty" in w for w in req.warnings)


def test_duplicate_skills_deduped():
    def dupe_router(system, user):
        return {"role_title": "X",
                "mandatory_skills": [{"name": "Python"}, {"name": "python"}],
                "preferred_skills": []}
    req = parse_jd("jd", MockProvider(dupe_router))
    assert len(req.mandatory_skills) == 1
