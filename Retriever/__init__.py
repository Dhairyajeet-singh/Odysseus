"""Stage 2: match structured resumes against a job description and rank them."""

from Parser.schema import (Requirements, Skill, Importance, Depth,
                     SkillAssessment, ScoreComponent, CandidateScore)
from Parser.providers import (LLMProvider, MockProvider, OpenAIProvider,
                        AnthropicProvider, get_provider, LLMError)
from Parser.jd_parser import parse_jd

__all__ = [
    "Requirements", "Skill", "Importance", "Depth", "SkillAssessment",
    "ScoreComponent", "CandidateScore",
    "LLMProvider", "MockProvider", "OpenAIProvider", "AnthropicProvider",
    "get_provider", "LLMError", "parse_jd",
]

from .embeddings import (Embedder, HashingEmbedder, OpenAIEmbedder,
                         SentenceTransformerEmbedder, get_embedder)
from .retriever import (Chunk, BM25, EvidenceChunk, SkillEvidence,
                        HybridRetriever, chunk_resume, retrieve_evidence, tokenize)

__all__ += [
    "Embedder", "HashingEmbedder", "OpenAIEmbedder",
    "SentenceTransformerEmbedder", "get_embedder",
    "Chunk", "BM25", "EvidenceChunk", "SkillEvidence", "HybridRetriever",
    "chunk_resume", "retrieve_evidence", "tokenize",
]

from LLM.evidence import assess_resume
__all__ += ["assess_resume"]
