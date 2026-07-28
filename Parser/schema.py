"""Stage 2 data model.

Stage 1 (resume_extract) turned documents into structured text. Stage 2 turns
that text plus a job description into a ranking. The types here are the contract
between the two stages and between the steps within stage 2:

    JD text        --parse-->  Requirements
    Requirements + resume  --retrieve+judge-->  [Assessment per requirement]
    [Assessment]   --score-->  CandidateScore
    [CandidateScore]  --rank-->  ranked output

Everything is a plain dataclass with a to_dict(), for the same reason stage 1
never returned a bare string: the final deliverable has to *explain itself*, and
you cannot explain a number you did not keep the parts of.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Importance(str, Enum):
    MANDATORY = "mandatory"    # "required", "must have"
    PREFERRED = "preferred"    # "nice to have", "bonus", "a plus"


@dataclass
class Skill:
    """A single required skill, with aliases for normalisation.

    `aliases` is what lets "JS" in a resume match "JavaScript" in the JD -- the
    skill-normalisation bonus feature lives here rather than being bolted on
    later.
    """
    name: str                       # canonical form, e.g. "JavaScript"
    importance: Importance = Importance.MANDATORY
    aliases: List[str] = field(default_factory=list)
    category: Optional[str] = None  # "language" | "cloud" | "framework" | ...
    # Distinct technologies, any ONE of which satisfies this requirement:
    # "PyTorch or TensorFlow" is one hurdle, not two. Aliases are different --
    # those are other names for the SAME thing ("JS" for JavaScript). Without
    # this, an either/or clause becomes two separate mandatory skills and a
    # candidate who meets it via the second one is marked as missing the first.
    alternatives: List[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        """How to show the requirement to a human: 'PyTorch or TensorFlow'."""
        return " or ".join([self.name] + self.alternatives)

    @property
    def search_terms(self) -> List[str]:
        """Everything that should retrieve evidence for this requirement."""
        return [self.name] + self.aliases + self.alternatives

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["importance"] = self.importance.value
        return d


@dataclass
class Requirements:
    """A job description, parsed into something matchable."""
    role_title: str = ""
    mandatory_skills: List[Skill] = field(default_factory=list)
    preferred_skills: List[Skill] = field(default_factory=list)
    min_years_experience: Optional[float] = None
    education: Optional[str] = None
    responsibilities: List[str] = field(default_factory=list)  # for semantic match
    raw_text: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def all_skills(self) -> List[Skill]:
        return self.mandatory_skills + self.preferred_skills

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_title": self.role_title,
            "mandatory_skills": [s.to_dict() for s in self.mandatory_skills],
            "preferred_skills": [s.to_dict() for s in self.preferred_skills],
            "min_years_experience": self.min_years_experience,
            "education": self.education,
            "responsibilities": self.responsibilities,
            "warnings": self.warnings,
        }


class Depth(str, Enum):
    """How strongly a resume demonstrates a skill -- not just present/absent.

    This is the distinction that stops keyword stuffing from working. A skill
    merely listed is weaker evidence than one used in a dated job bullet.
    """
    NONE = "none"           # not found
    MENTIONED = "mentioned"  # appears in a skills list only
    USED = "used"            # appears in an experience/project bullet
    STRONG = "strong"        # used, with scope/impact/duration attached


# Ordinal weight each depth contributes before importance weighting.
DEPTH_WEIGHT: Dict[Depth, float] = {
    Depth.NONE: 0.0,
    Depth.MENTIONED: 0.4,
    Depth.USED: 0.8,
    Depth.STRONG: 1.0,
}


@dataclass
class SkillAssessment:
    """The LLM's judgement about one skill -- evidence, not a score.

    The LLM fills `depth`, `evidence` and `where`. It never emits a number.
    The number is computed later, deterministically, from `depth` + the skill's
    importance. Keeping the model on the evidence side of that line is what
    makes the final score explainable and stable.
    """
    skill: str
    importance: Importance
    depth: Depth = Depth.NONE
    evidence: str = ""              # short quote/paraphrase from the resume
    where: Optional[str] = None     # section the evidence came from
    llm_confidence: Optional[float] = None  # 0-1, the model's own certainty

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["importance"] = self.importance.value
        d["depth"] = self.depth.value
        return d


@dataclass
class ScoreComponent:
    """One line of the score decomposition -- where a piece of the 0-100 came
    from, in plain terms."""
    label: str
    earned: float
    possible: float
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


"""Experience types.

These live in the schema rather than beside the parser that fills them, for the
same reason SkillAssessment does: they are part of the contract a CandidateScore
serialises, and putting them here keeps the dependency arrow pointing one way
(Ranker -> Parser, never back).
"""


@dataclass
class DateRange:
    """One employment interval, as inclusive month indices."""

    start_month: int          # year * 12 + month
    end_month: int
    is_current: bool
    raw: str

    @property
    def months(self) -> int:
        return max(0, self.end_month - self.start_month)

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "months": self.months,
                "years": round(self.months / 12.0, 2)}


@dataclass
class ExperienceEstimate:
    """How much professional experience the resume evidences, and how we know."""

    years: Optional[float] = None      # None == could not determine (not zero)
    method: str = "none"               # "date-ranges" | "claimed" | "none"
    ranges: List[DateRange] = field(default_factory=list)
    claimed_years: Optional[float] = None
    evidence: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.years is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "years": self.years,
            "method": self.method,
            "claimed_years": self.claimed_years,
            "ranges": [r.to_dict() for r in self.ranges],
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


@dataclass
class CandidateScore:
    """The full, explainable result for one candidate."""
    path: str
    score: float = 0.0              # 0-100
    rank: Optional[int] = None
    summary: str = ""
    matched_skills: List[str] = field(default_factory=list)
    missing_or_weak: List[str] = field(default_factory=list)
    components: List[ScoreComponent] = field(default_factory=list)
    assessments: List[SkillAssessment] = field(default_factory=list)
    extraction_confidence: float = 1.0   # carried from stage 1
    experience: Optional[ExperienceEstimate] = None
    # Duplicate handling. `duplicate_of` is set on a suppressed copy and points
    # at the representative that was ranked in its place; `duplicates` is the
    # mirror, listing the copies folded into this candidate. Exactly one of the
    # two is ever non-empty.
    duplicate_of: Optional[str] = None
    duplicates: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    @property
    def explanation(self) -> str:
        """Human-readable 'why this score' built from the components."""
        lines = [f"Score {self.score:.0f}/100 for {self.role_or_path()}:"]
        for c in self.components:
            lines.append(f"  - {c.label}: {c.earned:.0f} of {c.possible:.0f}"
                         f"{(' — ' + c.detail) if c.detail else ''}")
        if self.flags:
            lines.append("  flags: " + "; ".join(self.flags))
        return "\n".join(lines)

    def role_or_path(self) -> str:
        from pathlib import Path
        return Path(self.path).name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "score": round(self.score, 1),
            "rank": self.rank,
            "summary": self.summary,
            "matched_skills": self.matched_skills,
            "missing_or_weak": self.missing_or_weak,
            "explanation": self.explanation,
            "components": [c.to_dict() for c in self.components],
            "assessments": [a.to_dict() for a in self.assessments],
            "extraction_confidence": round(self.extraction_confidence, 3),
            "experience": self.experience.to_dict() if self.experience else None,
            "duplicate_of": self.duplicate_of,
            "duplicates": list(self.duplicates),
            "flags": self.flags,
        }