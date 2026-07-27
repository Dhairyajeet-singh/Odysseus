"""Stage 3: deterministic scoring and ranking from skill assessments."""

from .scoring import score_candidate, ScoringConfig
from .ranking import rank_candidates, rank_report

__all__ = ["score_candidate", "ScoringConfig", "rank_candidates", "rank_report"]
