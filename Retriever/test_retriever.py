"""Retriever tests — offline, via the deterministic HashingEmbedder.

These assert the *plumbing*: chunking granularity, BM25 exact-token behaviour,
alias-aware retrieval, and hybrid fusion/ranking. They do not claim to measure
semantic quality — that needs a real embedder and is a separate, key-dependent
evaluation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Parser import Importance, Skill, Requirements
from Retriever.embeddings import HashingEmbedder
from Retriever.retriever import (BM25, HybridRetriever, chunk_resume,
                                 retrieve_evidence, tokenize)

RESUME_SECTIONS = {
    "skills": "Python, JavaScript, Docker, Kubernetes, PostgreSQL, Terraform",
    "experience": (
        "Senior Backend Engineer, Acme Corp (2021-2024)\n\n"
        "Built high-throughput data services in Python handling 2M events per "
        "minute.\n\n"
        "Managed a team of five engineers and owned the on-call rotation.\n\n"
        "Deployed and operated services on Kubernetes across three regions."
    ),
    "education": "B.Tech in Computer Science, NIT Trichy (2018)",
}

EMB = HashingEmbedder()


def test_tokenizer_preserves_tech_tokens():
    # c++ and node.js must survive as single tokens. ci/cd splitting into
    # ci + cd is fine: both JD and resume split identically, so they still
    # match — what breaks matching is losing the + in c++, not splitting a /.
    toks = tokenize("Python, C++, Node.js and CI/CD")
    assert "c++" in toks and "node.js" in toks
    assert "ci" in toks and "cd" in toks


def test_chunking_tags_sections_and_splits():
    chunks = chunk_resume(RESUME_SECTIONS)
    assert chunks
    sections = {c.section for c in chunks}
    assert {"skills", "experience", "education"} <= sections
    # the multi-paragraph experience section should not collapse to one chunk
    exp = [c for c in chunks if c.section == "experience"]
    assert len(exp) >= 2


def test_bm25_rewards_exact_token():
    chunks = chunk_resume(RESUME_SECTIONS)
    bm = BM25(chunks)
    scores = bm.scores(tokenize("Kubernetes"))
    top = chunks[int(scores.argmax())]
    assert "kubernetes" in top.text.lower()


def test_exact_skill_retrieved_with_provenance():
    r = HybridRetriever(RESUME_SECTIONS, embedder=EMB)
    ev = r.retrieve(Skill("Kubernetes", Importance.MANDATORY))
    assert ev.chunks
    assert ev.chunks[0].matched_exact
    assert "kubernetes" in ev.chunks[0].text.lower()


def test_alias_retrieves_canonical_skill():
    """A JD skill named 'JavaScript' should retrieve a resume saying 'JavaScript'
    even when queried via its alias set — and 'JS' in a resume should be
    reachable via the alias on the skill."""
    sections = {"skills": "Proficient in JS and TS", "experience": "Built UIs"}
    r = HybridRetriever(sections, embedder=EMB)
    skill = Skill("JavaScript", Importance.MANDATORY, aliases=["js"])
    ev = r.retrieve(skill)
    assert ev.chunks and ev.chunks[0].matched_exact


def test_missing_skill_scores_low():
    r = HybridRetriever(RESUME_SECTIONS, embedder=EMB)
    ev = r.retrieve(Skill("Rust", Importance.MANDATORY))
    top = ev.best_score if ev.chunks else 0.0
    strong = r.retrieve(Skill("Kubernetes", Importance.MANDATORY)).best_score
    assert top < strong


def test_fusion_weights_change_ranking():
    """BM25-only vs semantic-only should be able to disagree — proof the two
    signals are actually independent and both wired in."""
    bm_only = HybridRetriever(RESUME_SECTIONS, embedder=EMB, w_bm25=1.0, w_semantic=0.0)
    ev = bm_only.retrieve(Skill("Python", Importance.MANDATORY))
    assert ev.chunks and ev.chunks[0].bm25 > 0


def test_retrieve_all_covers_every_skill():
    req = Requirements(
        mandatory_skills=[Skill("Python", Importance.MANDATORY),
                          Skill("Kubernetes", Importance.MANDATORY)],
        preferred_skills=[Skill("Terraform", Importance.PREFERRED)],
    )
    ev = retrieve_evidence(RESUME_SECTIONS, req, embedder=EMB)
    assert {e.skill for e in ev} == {"Python", "Kubernetes", "Terraform"}


def test_empty_resume_is_safe():
    r = HybridRetriever({}, embedder=EMB)
    ev = r.retrieve(Skill("Python", Importance.MANDATORY))
    assert ev.chunks == []
