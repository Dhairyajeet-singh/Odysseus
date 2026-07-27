# LLM/__init__.py
"""Stage 2c: the LLM judgement step — depth labels with grounding checks."""

from .evidence import assess_resume

__all__ = ["assess_resume"]