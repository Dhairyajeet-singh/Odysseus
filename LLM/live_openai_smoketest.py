"""Live smoke test for the OpenAI path — run this with YOUR key.

    export OPENAI_API_KEY=sk-...
    pip install openai
    python live_openai_smoketest.py

It runs one real resume through JD parsing, retrieval and evidence extraction,
and prints the grounded assessments. This is the check the offline mock tests
cannot make: that the real model actually reads a resume the way the prompt
intends. Costs a few cents.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from Parser import (OpenAIProvider, parse_jd)
from LLM.evidence import assess_resume
from Retriever import OpenAIEmbedder
from Retriever.retriever import HybridRetriever

JD = """
Senior Backend Engineer. 5+ years required. Must have strong Python and
Kubernetes experience. PostgreSQL required. Terraform is a plus.
"""

RESUME_SECTIONS = {
    "skills": "Python, JavaScript, Docker, Kubernetes, PostgreSQL",
    "experience": (
        "Senior Backend Engineer, Acme Corp (2021-2024)\n\n"
        "Built high-throughput data services in Python handling 2M events/min.\n\n"
        "Operated production workloads on Kubernetes across three AWS regions.\n\n"
        "Owned the PostgreSQL schema and query performance for the core product."
    ),
    "education": "B.Tech Computer Science, 2018",
}


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY first."); return 1

    provider = OpenAIProvider(model="gpt-4o-mini")
    embedder = OpenAIEmbedder(model="text-embedding-3-small")

    print("1) Parsing JD ...")
    req = parse_jd(JD, provider)
    print(f"   role: {req.role_title} | mandatory: "
          f"{[s.name for s in req.mandatory_skills]} | preferred: "
          f"{[s.name for s in req.preferred_skills]}")

    print("2) Retrieving evidence ...")
    ev = HybridRetriever(RESUME_SECTIONS, embedder=embedder).retrieve_all(req, top_k=3)

    print("3) Assessing (one LLM call) ...")
    assessments, warnings = assess_resume(req, ev, provider)
    for a in assessments:
        print(f"   {a.skill:12s} {a.importance.value:9s} depth={a.depth.value:9s} "
              f"conf={a.llm_confidence}  «{a.evidence[:60]}»")
    for w in warnings:
        print(f"   ! {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
