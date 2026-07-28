"""Evidence extraction — the LLM judgement step.

For each JD skill, decide *how strongly* the resume demonstrates it, based only
on the chunks retrieval surfaced. This is the one step where a language model
earns its place: judging whether "Kubernetes" is merely listed in a skills line
or actually operated in production is exactly the fuzzy reading task code is bad
at and an LLM is good at.

The hard architectural rule, enforced here: **the model returns evidence, not a
score.** It fills in a depth label, a supporting quote, and its own confidence.
It never emits the 0-100. That number is computed deterministically in the next
step from (depth × importance), which is what makes the final score explainable
and identical run to run. Letting the model emit the number would trade both
away for nothing.

Two safeguards around the model:

* **One call per resume.** All of a candidate's skills are judged in a single
  request against the union of their retrieved chunks — a few hundred calls for
  a whole batch instead of a few thousand. This is the cost-optimisation lever.
* **Grounding check.** Every quote the model returns is verified to actually
  occur in the supplied chunks. A quote that does not is a hallucination; the
  assessment is kept but flagged and its confidence cut, so an invented
  qualification cannot silently inflate a score.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from Parser.providers import LLMProvider
from Retriever.retriever import SkillEvidence
from Parser.schema import Depth, Importance, Requirements, SkillAssessment

_SYSTEM = """You are an expert technical recruiter assessing whether a candidate \
demonstrates specific skills, based ONLY on excerpts from their resume.

For each skill, assign a depth level:
- "none": the excerpts do not support this skill at all.
- "mentioned": the skill appears only in a list (e.g. a skills section), with no \
evidence of applying it.
- "used": the skill appears in the context of real work — a job or project \
bullet describing using it.
- "strong": the skill is used AND there is scope, impact, or duration attached \
(scale, metrics, years, ownership).

Strict rules:
- Judge ONLY from the provided excerpts. Do not use outside knowledge and do not \
assume skills that are not evidenced.
- Quote the exact text from the excerpts that supports your judgement. If depth \
is "none", use an empty string for evidence.
- Do not reward keyword stuffing: a bare list entry is "mentioned", never "used".
- Some skills list accepted alternatives, e.g. "PyTorch (or: TensorFlow)". \
Evidence for ANY of them satisfies that skill -- judge the depth of the \
strongest one found, and quote from it. Do not mark the skill absent because \
the candidate used the alternative rather than the first-named option.
- For "skill", return ONLY the first name listed, dropping any "(or: ...)" \
suffix. For "PyTorch (or: TensorFlow)" return exactly "PyTorch".

Return ONLY a JSON object of this exact shape:
{
  "assessments": [
    {"skill": string, "depth": "none|mentioned|used|strong",
     "evidence": string, "section": string|null, "confidence": number}
  ]
}
Include every skill you are asked about, in the same spelling."""

_VALID_DEPTH = {d.value: d for d in Depth}
_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-z0-9 ]+")


def _norm(text: str) -> str:
    return _WS.sub(" ", _NONWORD.sub(" ", text.lower())).strip()


def _is_grounded(evidence: str, haystack_norm: str) -> bool:
    """True if the quoted evidence really occurs in the supplied chunks.

    Tolerates minor paraphrase/whitespace by checking normalised token-window
    overlap rather than exact substring — models lightly reword quotes even
    when told not to, and we do not want to punish a faithful near-quote.
    """
    ev = _norm(evidence)
    if not ev:
        return True  # 'none' assessments legitimately have no quote
    if ev in haystack_norm:
        return True
    toks = ev.split()
    if len(toks) <= 3:
        return ev in haystack_norm
    # require a solid contiguous run to count as grounded
    window = " ".join(toks[:6])
    return window in haystack_norm


def _skill_key(name: str) -> str:
    """Normalise a skill name for matching.

    Drops parentheticals and every non-alphanumeric character, so
    "PyTorch (or: TensorFlow)", "pytorch", and "Py-Torch" all collapse to the
    same key. `+` and `#` survive because C++ and C# need them.
    """
    name = re.sub(r"\(.*?\)", " ", name)
    return re.sub(r"[^a-z0-9+#]+", "", name.lower())


def _build_user_prompt(req: Requirements, evidence: List[SkillEvidence]) -> str:
    lines: List[str] = []
    if req.role_title:
        lines.append(f"Role: {req.role_title}")
    if req.min_years_experience:
        lines.append(f"Experience expected: {req.min_years_experience}+ years")
    lines.append("")
    lines.append("Skills to assess:")
    # The line keeps the canonical name first so the model echoes it back
    # unchanged and the mapping below still matches; alternatives ride in a
    # suffix the model is told to strip.
    alts_by_skill = {sk.name: sk.alternatives for sk in req.all_skills
                     if getattr(sk, "alternatives", None)}
    for e in evidence:
        alts = alts_by_skill.get(e.skill)
        suffix = f" (or: {', '.join(alts)})" if alts else ""
        lines.append(f"- {e.skill}{suffix} ({e.importance.value})")
    lines.append("")
    lines.append("Relevant excerpts from the candidate's resume "
                 "(each tagged with the section it came from):")

    # Union of retrieved chunks, de-duplicated — the model sees each excerpt
    # once no matter how many skills retrieved it.
    seen = set()
    for e in evidence:
        for c in e.chunks:
            if c.chunk_id in seen:
                continue
            seen.add(c.chunk_id)
            lines.append(f"[{c.section}] {c.text}")
    if not seen:
        lines.append("(no relevant excerpts were found)")
    return "\n".join(lines)


def assess_resume(requirements: Requirements, evidence: List[SkillEvidence],
                  provider: LLMProvider) -> Tuple[List[SkillAssessment], List[str]]:
    """Judge every skill for one resume. Returns (assessments, warnings).

    Importance comes from the JD (via `evidence`), never from the model — it is
    a property of the job, not a judgement. The model only supplies depth,
    quote and confidence.
    """
    warnings: List[str] = []
    imp_by_skill: Dict[str, Importance] = {e.skill: e.importance for e in evidence}

    # Everything the model was shown, normalised once for grounding checks.
    haystack = _norm(" ".join(c.text for e in evidence for c in e.chunks))

    if not evidence:
        return [], ["no skills to assess"]

    try:
        data = provider.complete_json(_SYSTEM, _build_user_prompt(requirements, evidence))
    except Exception as exc:
        # Fail safe: every skill becomes 'none' rather than crashing the batch.
        return ([SkillAssessment(skill=e.skill, importance=e.importance)
                 for e in evidence],
                [f"evidence extraction failed: {exc}"])

    raw = data.get("assessments")
    if not isinstance(raw, list):
        return ([SkillAssessment(skill=e.skill, importance=e.importance)
                 for e in evidence],
                ["model returned no assessments array"])

    by_skill: Dict[str, dict] = {}
    for item in raw:
        if isinstance(item, dict) and item.get("skill"):
            by_skill[_skill_key(str(item["skill"]))] = item

    # Every spelling of a skill the model might plausibly answer under. The
    # model is asked for the canonical name, but prompt compliance is not
    # something to stake a candidate's score on: when a requirement is shown as
    # "PyTorch (or: TensorFlow)" models variously reply "PyTorch",
    # "TensorFlow", "PyTorch or TensorFlow", or the whole listed string. All of
    # them mean the same thing and none of them should read as an omission.
    accept: Dict[str, List[str]] = {}
    for sk in requirements.all_skills:
        alts = list(getattr(sk, "alternatives", []) or [])
        forms = [sk.name, *alts]
        if alts:
            forms += [" or ".join([sk.name] + alts),
                      "/".join([sk.name] + alts),
                      f"{sk.name} (or: {', '.join(alts)})"]
        accept[sk.name] = [_skill_key(f) for f in forms]

    out: List[SkillAssessment] = []
    for e in evidence:  # iterate the JD's skills, so none can be dropped
        item = None
        for key in accept.get(e.skill, [_skill_key(e.skill)]):
            item = by_skill.get(key)
            if item is not None:
                break
        if item is None:
            out.append(SkillAssessment(skill=e.skill, importance=e.importance))
            warnings.append(f"model omitted '{e.skill}' — treated as not found")
            continue

        depth = _VALID_DEPTH.get(str(item.get("depth", "none")).lower(), Depth.NONE)
        ev_text = str(item.get("evidence") or "").strip()
        section = item.get("section")
        try:
            conf = float(item.get("confidence"))
            conf = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            conf = None

        # Grounding: a non-'none' judgement must be backed by text actually shown.
        if depth != Depth.NONE and not _is_grounded(ev_text, haystack):
            warnings.append(
                f"'{e.skill}': quoted evidence not found in resume excerpts — "
                f"flagged as ungrounded, confidence reduced"
            )
            conf = (conf or 0.5) * 0.4
            ev_text = f"[unverified] {ev_text}" if ev_text else "[unverified]"

        out.append(SkillAssessment(
            skill=e.skill, importance=imp_by_skill[e.skill], depth=depth,
            evidence=ev_text, where=(str(section) if section else None),
            llm_confidence=conf,
        ))

    return out, warnings