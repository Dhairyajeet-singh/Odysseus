"""Background screening jobs, and the mapping into the frontend's shapes.

Screening two hundred resumes takes minutes, which is far too long to hold an
HTTP request open. So a POST starts a job and returns immediately with an id;
the browser polls for progress and collects the result when it is ready. That
also gives the ProcessingView something real to display — the log lines below
are emitted by the pipeline as it runs, not simulated on a timer.

Jobs live in memory. For a single-process deployment that is the right amount
of machinery; anything more (Redis, Celery) would be infrastructure this does
not need. The consequence is that a restart loses in-flight jobs, which is
noted rather than solved.
"""

from __future__ import annotations

import base64
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from OCR import extract, find_duplicates
from Parser import MockProvider, Requirements, get_provider, parse_jd
from Parser.schema import CandidateScore
from Retriever import HybridRetriever, get_embedder
from LLM import assess_resume
from Ranker import estimate_experience, rank_candidates, score_candidate

Status = Literal["queued", "running", "done", "error", "cancelled"]
LogType = Literal["info", "success", "warning", "error"]

# Scores in practice: a perfect match lands near 90, a strong-but-gapped
# candidate near 60, an off-field resume at 0. These bands are set against that
# observed distribution rather than an even split of 0-100.
BANDS = [(80, "MATCH FOUND"), (60, "STRONG"), (40, "MODERATE"), (20, "POTENTIAL")]


# ---------------------------------------------------------------------------
# job state


@dataclass
class Job:
    id: str
    total: int
    status: Status = "queued"
    completed: int = 0
    created: float = field(default_factory=time.time)
    logs: List[Dict[str, str]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    workdir: Optional[Path] = None
    _cancel: threading.Event = field(default_factory=threading.Event)

    def log(self, message: str, kind: LogType = "info") -> None:
        self.logs.append({"timestamp": datetime.now().strftime("%H:%M:%S"),
                          "message": message, "type": kind})

    def public(self, include_result: bool = True) -> Dict[str, Any]:
        out = {
            "jobId": self.id,
            "status": self.status,
            "completed": self.completed,
            "total": self.total,
            "progress": round(self.completed / self.total, 3) if self.total else 0.0,
            "elapsedSec": round(time.time() - self.created, 1),
            "logs": self.logs,
            "error": self.error,
        }
        if include_result:
            out["result"] = self.result
        return out


class JobStore:
    """Thread-safe registry with age-based eviction."""

    def __init__(self, max_age_sec: int = 3600, max_jobs: int = 50) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self.max_age_sec = max_age_sec
        self.max_jobs = max_jobs

    def create(self, total: int, workdir: Path) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], total=total, workdir=workdir)
        with self._lock:
            self._jobs[job.id] = job
            self._evict()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def remove(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and job.workdir:
            shutil.rmtree(job.workdir, ignore_errors=True)
        return job is not None

    def _evict(self) -> None:
        """Drop finished jobs that are old, then the oldest if still over cap.

        Uploaded resumes are personal data; leaving them on disk indefinitely
        because nobody called DELETE is not acceptable, so eviction removes the
        working directory too.
        """
        now = time.time()
        stale = [j for j in self._jobs.values()
                 if j.status in ("done", "error", "cancelled")
                 and now - j.created > self.max_age_sec]
        for job in stale:
            self._jobs.pop(job.id, None)
            if job.workdir:
                shutil.rmtree(job.workdir, ignore_errors=True)

        while len(self._jobs) > self.max_jobs:
            oldest = min(self._jobs.values(), key=lambda j: j.created)
            self._jobs.pop(oldest.id, None)
            if oldest.workdir:
                shutil.rmtree(oldest.workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# mapping into the frontend's shapes


def _status_for(score: float) -> str:
    for floor, label in BANDS:
        if score >= floor:
            return label
    return "LOW MATCH"


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?\d{5}[\s-]?\d{5}|\d{3}[\s-]?\d{3}[\s-]?\d{4}")


def _identity(sections: Dict[str, str], fallback: str) -> Dict[str, str]:
    """Name, role, and contact details out of the header block.

    The filename is a poor source — `Dhairyajeet_Singh_AI_Resume.pdf` is not a
    name — so the header section is read first and the filename only used when
    that fails.
    """
    header = (sections.get("header") or "").strip()
    lines = [ln.strip() for ln in header.splitlines() if ln.strip()]

    name, role = "", ""
    for ln in lines[:3]:
        if _EMAIL.search(ln) or "|" in ln and any(c.isdigit() for c in ln):
            continue
        # A name line is short, mostly alphabetic, and has few words.
        words = ln.split()
        if not name and 1 < len(words) <= 5 and sum(
                c.isalpha() or c.isspace() for c in ln) / max(len(ln), 1) > 0.85:
            name = ln.title() if ln.isupper() else ln
        elif name and not role and len(ln) < 80:
            role = ln
            break

    if not name:
        name = re.sub(r"[_-]+", " ", fallback).replace(".pdf", "").replace(
            ".docx", "").strip().title()

    whole = "\n".join(sections.values())
    email = (_EMAIL.search(whole) or [None])
    phone = _PHONE.search(header)
    return {"name": name or fallback,
            "currentRole": role,
            "email": email.group(0) if hasattr(email, "group") else "",
            "phone": phone.group(0).strip() if phone else ""}


def _avatar(name: str) -> str:
    """An initials SVG as a data URI.

    Deliberately not a stock photo service: showing a photograph of an unrelated
    person next to a real candidate's name is both misleading and a poor look in
    a hiring tool. Self-contained, so no third-party request carries candidate
    names off the machine either.
    """
    initials = "".join(w[0] for w in name.split()[:2] if w).upper() or "?"
    hue = sum(ord(c) for c in name) % 360
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96">'
           f'<rect width="96" height="96" rx="48" fill="hsl({hue},45%,32%)"/>'
           f'<text x="48" y="62" font-family="Arial,sans-serif" font-size="36" '
           f'font-weight="600" fill="#e2e8f0" text-anchor="middle">{initials}</text>'
           f'</svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(
        svg.encode("utf-8")).decode("ascii")


def to_frontend(c: CandidateScore, sections: Dict[str, str]) -> Dict[str, Any]:
    """One CandidateScore in the shape `src/types.ts` declares."""
    filename = Path(c.path).name
    who = _identity(sections, filename)

    demonstrated = [a for a in c.assessments
                    if a.depth.value in ("used", "strong")]
    strengths = [f"{a.skill} — {a.evidence[:110]}" if a.evidence else a.skill
                 for a in demonstrated[:4]]
    if not strengths:
        strengths = ["No skill was demonstrated in context; matches are "
                     "keyword-level only."]

    exp = c.experience
    years = (f"{exp.years:g} Yrs" if exp and exp.years is not None
             else "Not stated")

    return {
        "id": Path(c.path).stem,
        "name": who["name"],
        "currentRole": who["currentRole"] or "—",
        "matchScore": round(c.score),
        "skills": [s.upper() for s in c.matched_skills[:6]],
        "experienceYears": years,
        "status": _status_for(c.score),
        "summary": c.summary,
        "strengths": strengths,
        "gaps": c.missing_or_weak[:5] or ["No significant gaps identified."],
        "fileName": filename,
        "avatarUrl": _avatar(who["name"]),
        "email": who["email"],
        "phone": who["phone"],
        # Beyond the declared type, but the whole point of this system is that a
        # score can be defended. The UI can surface these or ignore them.
        "rank": c.rank,
        "explanation": c.explanation,
        "components": [{"label": k.label, "earned": k.earned,
                        "possible": k.possible, "detail": k.detail}
                       for k in c.components],
        "flags": c.flags,
        "extractionConfidence": round(c.extraction_confidence, 3),
        # Carried so the spreadsheet's Assessment column can show the depth
        # judgement and the quote behind every skill.
        "assessments": [{"skill": a.skill, "importance": a.importance.value,
                         "depth": a.depth.value, "evidence": a.evidence,
                         "where": a.where}
                        for a in c.assessments],
        "duplicateOf": c.duplicate_of if hasattr(c, "duplicate_of") else None,
    }


def summarise(cands: List[Dict[str, Any]], req: Requirements,
              elapsed: float) -> Dict[str, Any]:
    scores = [c["matchScore"] for c in cands] or [0]
    top = cands[0] if cands else None
    bands = [("90-100%", 90, 101), ("80-89%", 80, 90),
             ("70-79%", 70, 80), ("<70%", -1, 70)]
    rec = (f"{top['name']} leads at {top['matchScore']}/100 — {top['summary']}"
           if top else "No candidates could be scored.")
    return {
        "totalResumes": len(cands),
        "topScore": max(scores),
        "avgMatch": round(sum(scores) / len(scores), 1),
        "processingTimeSec": round(elapsed, 1),
        "aiRecommendation": rec,
        "scoreDistribution": [
            {"range": label,
             "count": sum(1 for s in scores if lo <= s < hi)}
            for label, lo, hi in bands],
    }


# ---------------------------------------------------------------------------
# the run


def run_job(job: Job, jd_text: str, resumes: List[Path],
            offline: bool = False, model: str = "gpt-4o-mini",
            workers: int = 8, top_k: int = 3) -> None:
    """Execute one screening job. Runs on a worker thread."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    started = time.time()
    job.status = "running"
    try:
        if offline:
            from main import _offline_router
            provider = MockProvider(_offline_router)
            embedder = get_embedder("hashing")
            job.log("Running offline — stub model, no network", "warning")
        else:
            provider = get_provider("openai", model=model)
            embedder = get_embedder("openai")

        job.log("Parsing job description")
        req = parse_jd(jd_text, provider)
        if not req.all_skills:
            raise RuntimeError(
                "No requirements could be read from the job description. "
                + " ".join(req.warnings))
        job.log(f"Requirements: {len(req.mandatory_skills)} required, "
                f"{len(req.preferred_skills)} preferred", "success")
        for w in req.warnings:
            job.log(w, "warning")

        job.log(f"Screening {len(resumes)} resume(s) across {workers} workers")
        scored: List[CandidateScore] = []
        sections_by_path: Dict[str, Dict[str, str]] = {}
        extractions = []

        def one(path: Path):
            r = extract(path)
            if not r.ok:
                return path, None, r, (r.error or "no readable text")
            ev = HybridRetriever(r.sections, embedder=embedder).retrieve_all(
                req, top_k=top_k)
            assessments, warnings = assess_resume(req, ev, provider)
            s = score_candidate(req, assessments, path=str(path),
                                extraction_confidence=r.confidence,
                                experience=estimate_experience(r.sections))
            s.flags.extend(warnings)
            return path, s, r, None

        failures: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(one, p): p for p in resumes}
            for fut in as_completed(futures):
                if job._cancel.is_set():
                    job.status = "cancelled"
                    job.log("Cancelled by request", "warning")
                    return
                path = futures[fut]
                try:
                    path, s, r, err = fut.result()
                except Exception as exc:            # noqa: BLE001
                    failures.append({"file": path.name,
                                     "error": f"{type(exc).__name__}: {exc}"})
                    job.log(f"{path.name}: {type(exc).__name__}", "error")
                else:
                    if r is not None:
                        extractions.append(r)
                    if s is None:
                        failures.append({"file": path.name, "error": err or ""})
                        job.log(f"{path.name}: {err}", "error")
                    else:
                        scored.append(s)
                        sections_by_path[str(path)] = r.sections
                        job.log(f"{path.name} — {s.score:.0f}/100")
                job.completed += 1

        duplicates = []
        if len(scored) > 1:
            try:
                duplicates = find_duplicates(extractions)
                if duplicates:
                    job.log(f"{len(duplicates)} near-duplicate pair(s) detected",
                            "warning")
            except Exception:                       # noqa: BLE001
                duplicates = []

        try:
            ranked = rank_candidates(scored, duplicates=duplicates)
        except TypeError:                           # older Ranker signature
            ranked = rank_candidates(scored)

        elapsed = time.time() - started
        cands = [to_frontend(c, sections_by_path.get(c.path, {}))
                 for c in ranked if c.rank is not None]
        folded = [to_frontend(c, sections_by_path.get(c.path, {}))
                  for c in ranked if c.rank is None]

        job.result = {
            "jobTitle": req.role_title or "Untitled role",
            "requirements": {
                "mandatory": [s.display if hasattr(s, "display") else s.name
                              for s in req.mandatory_skills],
                "preferred": [s.display if hasattr(s, "display") else s.name
                              for s in req.preferred_skills],
                "minYearsExperience": req.min_years_experience,
            },
            "candidates": cands,
            "duplicatesFolded": folded,
            "unreadable": failures,
            "summary": summarise(cands, req, elapsed),
        }
        job.status = "done"
        job.log(f"Completed in {elapsed:.1f}s — {len(cands)} ranked, "
                f"{len(failures)} unreadable", "success")

    except Exception as exc:                        # noqa: BLE001
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
        job.log(job.error, "error")