"""Job-description parser: raw JD text -> structured Requirements.

This is the missing half of the extraction stage. Stage 1 structured the
resumes; nothing yet structures the JD, and you cannot match against a JD you
have not structured. In particular, the "weight mandatory vs preferred skills"
bonus is impossible unless something first *separates* mandatory from preferred
-- which is exactly this module's job.

Design: the LLM extracts the requirements into a fixed schema, then a
deterministic layer validates and normalises the result. The split matters --
the model is good at reading unstructured prose ("you'll need strong Python;
Kubernetes is a plus") and bad at being trusted blindly, so its output is
treated as a proposal that code then checks: importance values are coerced to
the enum, obvious skill aliases are attached, and anything malformed is dropped
with a warning rather than crashing the run.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .providers import LLMProvider
from .schema import Importance, Requirements, Skill

_SYSTEM = """You are an expert technical recruiter. Extract the hiring \
requirements from a job description into structured JSON.

Rules:
- Separate skills into "mandatory" (required, must-have, essential) and \
"preferred" (nice-to-have, bonus, a plus, desirable).
- Use canonical skill names: "JavaScript" not "JS", "PostgreSQL" not "postgres".
- When the JD offers a choice -- "PyTorch or TensorFlow", "AWS/Azure/GCP", \
"FastAPI or Flask" -- emit ONE skill with the first option as "name" and the \
rest in "alternatives". Never split a choice into separate skills: that would \
force a candidate to have all of them.
- "alternatives" is for genuinely different technologies that each satisfy the \
requirement. It is NOT for other names of the same thing.
- Only include concrete, checkable skills/technologies/qualifications. Do not \
invent requirements that are not stated.
- If seniority implies years of experience, extract min_years_experience as a \
number; otherwise null.

Return ONLY a JSON object with this exact shape:
{
  "role_title": string,
  "mandatory_skills": [{"name": string, "alternatives": [string], \
"category": string|null}],
  "preferred_skills": [{"name": string, "alternatives": [string], \
"category": string|null}],
  "min_years_experience": number|null,
  "education": string|null,
  "responsibilities": [string]
}"""

# Common alias map applied deterministically after the LLM pass, so
# normalisation does not depend on the model remembering to do it every time.
_ALIASES: Dict[str, List[str]] = {
    "JavaScript": ["js", "java script", "ecmascript"],
    "TypeScript": ["ts"],
    "PostgreSQL": ["postgres", "psql", "postgre"],
    "Kubernetes": ["k8s"],
    "Amazon Web Services": ["aws"],
    "Google Cloud Platform": ["gcp", "google cloud"],
    "Microsoft Azure": ["azure"],
    "Continuous Integration": ["ci", "ci/cd", "cicd"],
    "Natural Language Processing": ["nlp"],
    "Machine Learning": ["ml"],
    "React": ["react.js", "reactjs"],
    "Node.js": ["node", "nodejs"],
    "C++": ["cpp", "cplusplus"],
    "C#": ["c sharp", "csharp"],
}


def _aliases_for(name: str) -> List[str]:
    key = name.strip()
    if key in _ALIASES:
        return list(_ALIASES[key])
    low = key.lower()
    for canon, al in _ALIASES.items():
        if low == canon.lower() or low in al:
            return sorted((set(al) | {canon.lower()}) - {low})
    return []


def _skills(raw: Any, importance: Importance, warnings: List[str]) -> List[Skill]:
    out: List[Skill] = []
    if not isinstance(raw, list):
        return out
    seen = set()
    for item in raw:
        alts: List[str] = []
        if isinstance(item, str):
            name, category = item.strip(), None
        elif isinstance(item, dict) and item.get("name"):
            name, category = str(item["name"]).strip(), item.get("category")
            raw_alts = item.get("alternatives") or []
            if isinstance(raw_alts, list):
                alts = [str(a).strip() for a in raw_alts
                        if str(a).strip() and str(a).strip().lower() != name.lower()]
        else:
            warnings.append(f"dropped malformed skill entry: {item!r}")
            continue
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        seen.update(a.lower() for a in alts)   # an alternative is not its own skill
        # Alternatives need their aliases expanded too, or a requirement written
        # as "Computer vision or Natural Language Processing" fails to match a
        # resume that only ever writes "NLP".
        alias_pool = list(_aliases_for(name))
        for alt in alts:
            alias_pool.append(alt)
            alias_pool.extend(_aliases_for(alt))
        low_name = name.lower()
        aliases = sorted({a.lower() for a in alias_pool if a and a.lower() != low_name})

        out.append(Skill(name=name, importance=importance,
                         aliases=aliases, category=category,
                         alternatives=alts))
    return out


def parse_jd(text: str, provider: LLMProvider) -> Requirements:
    """Parse a job description into structured Requirements.

    Never raises on a bad model response; malformed pieces become warnings so a
    single odd JD cannot halt a batch run.
    """
    text = (text or "").strip()
    if not text:
        return Requirements(warnings=["empty job description"])

    warnings: List[str] = []
    try:
        data = provider.complete_json(_SYSTEM, text)
    except Exception as exc:
        return Requirements(raw_text=text,
                            warnings=[f"JD parse failed: {exc}"])

    req = Requirements(
        role_title=str(data.get("role_title") or "").strip(),
        mandatory_skills=_skills(data.get("mandatory_skills"),
                                 Importance.MANDATORY, warnings),
        preferred_skills=_skills(data.get("preferred_skills"),
                                 Importance.PREFERRED, warnings),
        education=(str(data["education"]).strip()
                   if data.get("education") else None),
        responsibilities=[str(r).strip() for r in data.get("responsibilities", [])
                          if str(r).strip()],
        raw_text=text,
        warnings=warnings,
    )

    yrs = data.get("min_years_experience")
    if isinstance(yrs, (int, float)):
        req.min_years_experience = float(yrs)
    elif yrs is not None:
        warnings.append(f"ignored non-numeric min_years_experience: {yrs!r}")

    if not req.mandatory_skills and not req.preferred_skills:
        warnings.append("no skills extracted — JD may be unusually formatted")

    return req