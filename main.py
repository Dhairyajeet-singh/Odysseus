#!/usr/bin/env python3
"""main.py — resume screening and ranking, end to end.

Point it at one job description and a folder of resumes; it reads every file,
scores each candidate against the JD, and prints a ranked list with the reason
for each score.

    python main.py --jd jd.txt --resumes ./resumes
    python main.py --jd jd.txt --resumes ./resumes --out results.json
    python main.py --jd jd.txt --resumes ./resumes --offline   # no API key needed

Set your key first (real runs):

    Windows      $env:OPENAI_API_KEY = "sk-..."
    macOS/Linux  export OPENAI_API_KEY="sk-..."

Pipeline, in order:

    resume  ->  OCR extract  ->  retrieve  ->  LLM judges depth  ->  score
    JD      ->  parse (once)  /                                        |
                                                              rank + dedupe
                                                                       |
                                                              printed + JSON

Two properties worth knowing about the design:

* **The LLM never produces the score.** It reports, per skill, how deeply the
  resume evidences it, and quotes the line it read that from. The 0-100 is
  arithmetic over those labels, so it is reproducible and every point is
  traceable to a quote.
* **One LLM call per resume, one per run.** The JD is parsed once for the whole
  batch. 200 resumes costs 201 calls, not thousands.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from OCR import Config, extract, find_duplicates
from Parser import MockProvider, Requirements, get_provider, parse_jd
from Parser.schema import CandidateScore
from Retriever import HybridRetriever, get_embedder
from LLM import assess_resume
from Ranker import estimate_experience, rank_candidates, score_candidate

RESUME_SUFFIXES = {".pdf", ".docx", ".doc"}


# ---------------------------------------------------------------------------
# .env


def load_env(path: Optional[Path] = None) -> Optional[Path]:
    """Load KEY=VALUE pairs from a .env file next to this script.

    Uses python-dotenv when it is installed, and falls back to a small parser
    otherwise so the project works straight after `pip install -r
    requirements.txt` without an extra dependency.

    Real environment variables always win: if OPENAI_API_KEY is already set in
    the shell, the .env value does not clobber it. That is standard dotenv
    behaviour and it means a one-off `$env:OPENAI_API_KEY=...` still overrides
    the file for a single run.
    """
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return None

    try:
        from dotenv import load_dotenv          # optional
        load_dotenv(env_path, override=False)
        return env_path
    except ImportError:
        pass

    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):   # tolerate shell-style files
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:        # never clobber the real env
            os.environ[key] = value
    return env_path


# ---------------------------------------------------------------------------
# input


def collect_resumes(target: str) -> List[Path]:
    """Every resume under a folder, or the single file given."""
    p = Path(target)
    if p.is_file():
        return [p]
    if not p.is_dir():
        raise SystemExit(f"error: no such file or folder: {target}")
    found = sorted(f for f in p.rglob("*")
                   if f.is_file() and f.suffix.lower() in RESUME_SUFFIXES)
    if not found:
        raise SystemExit(f"error: no PDF or DOCX files found under {target}")
    return found


def read_jd(target: str) -> str:
    """The JD as text — a file path if it points at one, otherwise the string."""
    p = Path(target)
    if p.is_file():
        if p.suffix.lower() in RESUME_SUFFIXES:      # a JD supplied as a PDF
            r = extract(p)
            if not r.ok:
                raise SystemExit(f"error: could not read JD: {r.error}")
            return r.text
        return p.read_text(encoding="utf-8", errors="replace")
    return target


# ---------------------------------------------------------------------------
# one candidate


def screen_one(path: Path, req: Requirements, provider, embedder,
               top_k: int = 3, cfg: Optional[Config] = None
               ) -> tuple[Optional[CandidateScore], Optional[str], object]:
    """Run one resume all the way through. Returns (score, error, extraction).

    Errors are returned rather than raised: in a batch of 200, one corrupt PDF
    at position 37 must not end the run.

    The raw extraction comes back too so duplicate detection can reuse it.
    Re-reading the files afterwards would double the OCR bill, which on a
    scanned batch is by far the most expensive thing the pipeline does.
    """
    r = None
    try:
        r = extract(path, cfg) if cfg else extract(path)
        if not r.ok:
            return None, r.error or "no readable text", r

        evidence = HybridRetriever(r.sections, embedder=embedder).retrieve_all(
            req, top_k=top_k)
        assessments, warnings = assess_resume(req, evidence, provider)

        score = score_candidate(
            req, assessments,
            path=str(path),
            extraction_confidence=r.confidence,
            experience=estimate_experience(r.sections),
        )
        score.flags.extend(warnings)
        return score, None, r
    except Exception as exc:                       # noqa: BLE001 — isolate it
        return None, f"{type(exc).__name__}: {exc}", r


# ---------------------------------------------------------------------------
# the run


def screen(jd_text: str, resumes: Sequence[Path], provider, embedder,
           workers: int = 8, top_k: int = 3, quiet: bool = False):
    """Parse the JD once, screen every resume, rank the results."""
    t0 = time.perf_counter()

    if not quiet:
        print(f"Reading job description...")
    req = parse_jd(jd_text, provider)

    # parse_jd never raises — a provider failure comes back as empty
    # requirements plus a warning. Screening a whole batch against zero skills
    # would burn one API call per resume and rank everyone at zero, so stop
    # here instead and say why.
    if not req.all_skills:
        detail = "\n".join(f"  {w}" for w in req.warnings) or \
                 "  the model returned no skills"
        raise SystemExit(
            f"error: no requirements could be read from the job description.\n"
            f"{detail}\n\n"
            f"Check the JD has a skills or requirements section, and that your "
            f"OPENAI_API_KEY is valid.")

    if not quiet:
        mand = ", ".join(s.name for s in req.mandatory_skills) or "none"
        pref = ", ".join(s.name for s in req.preferred_skills) or "none"
        print(f"  role      : {req.role_title or 'not stated'}")
        print(f"  required  : {mand}")
        print(f"  preferred : {pref}")
        if req.min_years_experience:
            print(f"  experience: {req.min_years_experience:g}+ years")
        print(f"\nScreening {len(resumes)} resume(s) with {workers} workers...")

    scores: List[CandidateScore] = []
    failures: List[tuple[str, str]] = []
    extractions = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(screen_one, p, req, provider, embedder, top_k): p
                   for p in resumes}
        for i, fut in enumerate(as_completed(futures), 1):
            path = futures[fut]
            result, error, extraction = fut.result()
            if extraction is not None:
                extractions.append(extraction)
            if result is not None:
                scores.append(result)
            else:
                failures.append((path.name, error or "unknown"))
            if not quiet:
                mark = "." if result is not None else "x"
                print(mark, end="", flush=True)
                if i % 50 == 0:
                    print(f"  {i}/{len(resumes)}")
    if not quiet:
        print()

    # Duplicate detection runs after extraction, on the text we already have,
    # so a badly-scanned copy is compared on what OCR actually recovered.
    duplicates = []
    if len(scores) > 1:
        try:
            duplicates = find_duplicates(extractions)
        except Exception:
            duplicates = []

    ranked = rank_candidates(scores, duplicates=duplicates)
    return req, ranked, failures, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# output


BAR = "─" * 78


def show(req: Requirements, ranked: Sequence[CandidateScore],
         failures: Sequence[tuple[str, str]], elapsed: float,
         detail: bool = False) -> None:
    shortlist = [c for c in ranked if c.rank is not None]
    folded = [c for c in ranked if c.rank is None]

    print(f"\n{BAR}")
    print(f"RANKING — {req.role_title or 'role not stated'}"
          f"   ({len(shortlist)} candidates, {elapsed:.1f}s)")
    print(BAR)

    for c in shortlist:
        print(f"\n#{c.rank}  {c.score:.0f}/100   {Path(c.path).name}")
        print(f"    {c.summary}")

        if c.matched_skills:
            print(f"    matched : {', '.join(c.matched_skills)}")
        if c.missing_or_weak:
            print(f"    gaps    : {', '.join(c.missing_or_weak)}")

        for comp in c.components:
            print(f"      {comp.label:<22} {comp.earned:5.1f} / {comp.possible:<5.1f}"
                  f"  {comp.detail}")

        for f in c.flags:
            print(f"    ! {f}")

        if detail:
            for a in c.assessments:
                if a.evidence:
                    print(f"      · {a.skill} [{a.depth.value}] \"{a.evidence[:70]}\"")

    if folded:
        print(f"\n{BAR}")
        print(f"FOLDED IN — {len(folded)} duplicate submission(s)")
        for c in folded:
            print(f"  {Path(c.path).name}  ->  same as "
                  f"{Path(c.duplicate_of).name}")

    if failures:
        print(f"\n{BAR}")
        print(f"COULD NOT READ — {len(failures)} file(s)")
        for name, err in failures:
            print(f"  {name}: {err}")

    print(f"\n{BAR}")


def to_json(req: Requirements, ranked: Sequence[CandidateScore],
            failures: Sequence[tuple[str, str]], elapsed: float) -> dict:
    return {
        "job": req.to_dict(),
        "generated_seconds": round(elapsed, 2),
        "shortlist": [c.to_dict() for c in ranked if c.rank is not None],
        "duplicates_folded": [c.to_dict() for c in ranked if c.rank is None],
        "unreadable": [{"file": n, "error": e} for n, e in failures],
    }


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="Screen and rank resumes against one job description.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="example:\n"
               "  python main.py --jd jd.txt --resumes ./resumes --out out.json")
    ap.add_argument("--jd", required=True,
                    help="job description: a .txt/.md/.pdf path, or the text itself")
    ap.add_argument("--resumes", required=True,
                    help="a folder of resumes, or a single PDF/DOCX")
    ap.add_argument("--out", help="write the full result to this JSON file")
    ap.add_argument("--top", type=int, help="only print the top N candidates")
    ap.add_argument("--workers", type=int, default=8,
                    help="resumes screened in parallel (default 8)")
    ap.add_argument("--top-k", type=int, default=3, dest="top_k",
                    help="chunks retrieved per skill (default 3)")
    ap.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    ap.add_argument("--env-file", dest="env_file",
                    help="path to a .env file (default: .env beside main.py)")
    ap.add_argument("--offline", action="store_true",
                    help="run with stub LLM and hashing embeddings — no API key, "
                         "no network; useful for checking the plumbing")
    ap.add_argument("--detail", action="store_true",
                    help="also print the quoted evidence behind each skill")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    env_file = load_env(Path(args.env_file) if args.env_file else None)

    resumes = collect_resumes(args.resumes)
    jd_text = read_jd(args.jd)
    if not jd_text.strip():
        raise SystemExit("error: the job description is empty")

    if args.offline:
        provider = MockProvider(_offline_router)
        embedder = get_embedder("hashing")
        if not args.quiet:
            print("running offline — stub LLM, no network\n")
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            where = f"\n(read {env_file}, but it has no OPENAI_API_KEY)" if env_file \
                    else "\n(no .env file found next to main.py)"
            raise SystemExit(
                "error: OPENAI_API_KEY is not set." + where + "\n\n"
                "Create a file named .env in the project root containing:\n"
                "  OPENAI_API_KEY=sk-...\n\n"
                "Or set it for one shell:\n"
                "  Windows      $env:OPENAI_API_KEY = \"sk-...\"\n"
                "  macOS/Linux  export OPENAI_API_KEY=\"sk-...\"\n\n"
                "Or run with --offline to check the pipeline without a key.")
        if env_file and not args.quiet:
            print(f"loaded {env_file.name}")
        provider = get_provider("openai", model=args.model)
        embedder = get_embedder("openai")

    req, ranked, failures, elapsed = screen(
        jd_text, resumes, provider, embedder,
        workers=args.workers, top_k=args.top_k, quiet=args.quiet)

    shown = ranked
    if args.top:
        keep = [c for c in ranked if c.rank is not None][:args.top]
        shown = keep + [c for c in ranked if c.rank is None]
    show(req, shown, failures, elapsed, detail=args.detail)

    if args.out:
        Path(args.out).write_text(
            json.dumps(to_json(req, ranked, failures, elapsed), indent=2),
            encoding="utf-8")
        print(f"written: {args.out}")

    return 0 if ranked else 1


# ---------------------------------------------------------------------------
# offline stub — lets the whole pipeline run with no API key.
# Depth is derived from WHERE a skill appears: a skills list is "mentioned",
# an experience bullet is "used", one with numbers in it is "strong".


def _offline_router(system: str, user: str) -> dict:
    import re

    if "hiring requirements" in system or "job description" in system.lower():
        # A stub, not a model: match the JD against a small vocabulary of real
        # tools rather than guessing from capitalisation, which picks up "We"
        # and "Nice" and makes the offline demo look broken.
        vocab = (
            "python java javascript typescript go golang rust c++ c# ruby php scala kotlin swift "
            "sql postgresql mysql mongodb redis cassandra elasticsearch snowflake bigquery "
            "kafka spark flink airflow hadoop dbt kinesis "
            "aws azure gcp kubernetes docker terraform ansible jenkins "
            "pytorch tensorflow scikit-learn pandas numpy langchain "
            "react angular vue django flask fastapi node express graphql rest "
            "git linux bash ci/cd microservices"
        ).split()

        low = user.lower()
        # Split the JD on its own headings so required and preferred separate.
        cut = re.split(r"(?i)\b(?:nice to have|preferred|bonus|desirable)\b", low, 1)
        required_text = cut[0]
        preferred_text = cut[1] if len(cut) > 1 else ""

        nice = {"sql": "SQL", "aws": "AWS", "gcp": "GCP", "ci/cd": "CI/CD",
                "pytorch": "PyTorch", "tensorflow": "TensorFlow",
                "postgresql": "PostgreSQL", "mysql": "MySQL",
                "mongodb": "MongoDB", "javascript": "JavaScript",
                "typescript": "TypeScript", "graphql": "GraphQL",
                "bigquery": "BigQuery", "scikit-learn": "scikit-learn",
                "numpy": "NumPy", "fastapi": "FastAPI", "nodejs": "Node.js",
                "c++": "C++", "c#": "C#", "rest": "REST", "dbt": "dbt"}

        def pick(block: str) -> list:
            hits = []
            for term in vocab:
                if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", block):
                    hits.append(nice.get(term, term.title()))
            return hits

        mand = pick(required_text)
        pref = [t for t in pick(preferred_text) if t not in mand]

        title = ""
        for line in user.strip().splitlines():
            if line.strip():
                title = line.strip()[:60]
                break

        years = re.search(r"(\d{1,2})\s*\+?\s*years?", low)
        return {
            "role_title": title or "Role",
            "mandatory_skills": [{"name": w} for w in mand[:8]],
            "preferred_skills": [{"name": w} for w in pref[:6]],
            "min_years_experience": float(years.group(1)) if years else None,
            "responsibilities": [],
        }

    skills = [m.group(1).strip() for m in
              re.finditer(r"^- (.+?) \((?:mandatory|preferred)\)$", user,
                          re.MULTILINE)]
    tail = user.split("section it came from):", 1)[-1]
    excerpts = [(m.group(1), m.group(2).strip()) for m in
                re.finditer(r"\[(\w+)\]\s*(.*?)(?=\n\[\w+\]|\Z)", tail, re.DOTALL)]

    out = []
    for skill in skills:
        depth, evidence = "none", ""
        for section, body in excerpts:
            if skill.lower() not in body.lower():
                continue
            if section in ("experience", "projects"):
                depth = "strong" if any(ch.isdigit() for ch in body) else "used"
            elif depth == "none":
                depth = "mentioned"
            i = body.lower().index(skill.lower())
            evidence = body[max(0, i - 30):i + 40].strip()
            if depth in ("used", "strong"):
                break
        out.append({"skill": skill, "depth": depth, "evidence": evidence,
                    "confidence": 0.9})
    return {"assessments": out}


if __name__ == "__main__":
    raise SystemExit(main())