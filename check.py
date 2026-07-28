#!/usr/bin/env python3
"""check.py — verify every module in the pipeline with one command.

    python check.py              # everything except live API calls
    python check.py --fast       # skip the OCR suite (it rasterises + OCRs)
    python check.py --live       # also hit the real OpenAI API (needs a key)
    python check.py -v           # show full pytest output for failures

Five layers, cheapest first, so the first thing that breaks is the first thing
you see:

    1. environment   are the dependencies and the tesseract binary present
    2. imports       does every package expose what it claims to
    3. unit tests    each module's own pytest suite, reported separately
    4. integration   stage 1 -> 2 -> 3 end to end, offline, with MockProvider
    5. live          one real OpenAI round-trip (opt-in)

Layer 4 is the one the per-module suites cannot cover: each stage is tested in
isolation, so nothing else checks that OCR's `sections` dict is actually the
shape the retriever wants, or that a real extraction confidence reaches the
scorer. Exit code is 0 only if every selected layer passes.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# --------------------------------------------------------------------------
# reporting

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


PASS, FAIL, SKIP, WARN = (
    _c("PASS", "32"), _c("FAIL", "31"), _c("SKIP", "90"), _c("WARN", "33"),
)

results: list[tuple[str, str, str]] = []   # (layer, name, status)


def record(layer: str, name: str, status: str, note: str = "") -> None:
    results.append((layer, name, status))
    line = f"  {status}  {name}"
    if note:
        line += _c(f"  — {note}", "90")
    print(line)


def header(text: str) -> None:
    print(f"\n{_c(text, '1')}")


# --------------------------------------------------------------------------
# 1. environment


REQUIRED = {
    "numpy": "numpy",
    "fitz": "pymupdf",
    "pdfplumber": "pdfplumber",
    "docx": "python-docx",
    "pytesseract": "pytesseract",
    "PIL": "pillow",
    "pytest": "pytest",
}
OPTIONAL = {"openai": "openai", "reportlab": "reportlab (fixtures only)"}


def check_environment(fast: bool) -> None:
    header("1. environment")
    missing_pkgs: list[str] = []
    py = sys.version_info
    record("env", f"python {py.major}.{py.minor}.{py.micro}",
           PASS if py >= (3, 10) else FAIL,
           "" if py >= (3, 10) else "needs 3.10+ (uses `X | Y` type syntax)")

    # Which interpreter is actually running matters more than it looks. On
    # Windows, `py script.py` invokes the launcher, which may resolve to a
    # system Python even when a venv is active — so `pip install` succeeds and
    # every import still fails. Surfacing the path makes that self-evident.
    venv = os.environ.get("VIRTUAL_ENV")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(_c(f"       interpreter: {sys.executable}", "90"))
    if venv and not in_venv:
        record("env", "virtualenv", FAIL,
               f"{venv} is activated but NOT the interpreter running this "
               f"script — use `python check.py`, not `py check.py`")
    elif in_venv:
        record("env", "virtualenv", PASS, sys.prefix)
    else:
        record("env", "virtualenv", WARN, "none active — using system Python")

    for mod, pkg in REQUIRED.items():
        try:
            importlib.import_module(mod)
            record("env", pkg, PASS)
        except ImportError:
            missing_pkgs.append(pkg)
            record("env", pkg, FAIL, "pip install -r requirements.txt")

    for mod, pkg in OPTIONAL.items():
        try:
            importlib.import_module(mod)
            record("env", pkg, PASS)
        except ImportError:
            record("env", pkg, SKIP, "optional")

    exe = shutil.which("tesseract") or _windows_tesseract()
    if exe:
        record("env", "tesseract binary", PASS)
    else:
        if sys.platform == "win32":
            hint = ("install from github.com/UB-Mannheim/tesseract/wiki "
                    "and tick 'Add to PATH'")
        elif sys.platform == "darwin":
            hint = "brew install tesseract"
        else:
            hint = "sudo apt-get install tesseract-ocr"
        record("env", "tesseract binary", SKIP if fast else FAIL,
               f"{hint} — needed only for the OCR fallback path")

    if missing_pkgs:
        print(_c(f"\n     {len(missing_pkgs)} package(s) missing. Install with:",
                 "33"))
        print(_c("       pip install -r requirements.txt", "33"))


def _windows_tesseract() -> str | None:
    """Tesseract's Windows installer does not always add itself to PATH."""
    if sys.platform != "win32":
        return None
    for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                 os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA", "")):
        if not base:
            continue
        exe = Path(base) / "Tesseract-OCR" / "tesseract.exe"
        if exe.exists():
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = str(exe)
            except ImportError:
                pass
            return str(exe)
    return None


# --------------------------------------------------------------------------
# 2. imports — does each package expose its advertised surface?


EXPECTED_EXPORTS = {
    "OCR": ["Config", "extract", "extract_batch", "find_duplicates",
            "ExtractionResult"],
    "Parser": ["Requirements", "Skill", "Importance", "Depth", "CandidateScore",
               "MockProvider", "get_provider", "parse_jd"],
    "Retriever": ["HybridRetriever", "BM25", "chunk_resume", "retrieve_evidence",
                  "get_embedder", "HashingEmbedder"],
    "LLM": ["assess_resume"],
    "Ranker": ["score_candidate", "ScoringConfig", "rank_candidates",
               "rank_report"],
}


def check_imports() -> None:
    header("2. package imports")
    for pkg, names in EXPECTED_EXPORTS.items():
        try:
            mod = importlib.import_module(pkg)
        except Exception as exc:
            record("import", pkg, FAIL, f"{type(exc).__name__}: {exc}")
            continue
        missing = [n for n in names if not hasattr(mod, n)]
        if missing:
            record("import", pkg, FAIL, "missing: " + ", ".join(missing))
        else:
            record("import", pkg, PASS, f"{len(names)} symbols")


# --------------------------------------------------------------------------
# 3. unit tests — each module's suite, run separately


SUITES = {
    "OCR": "OCR/test_extraction.py",
    "Parser": "Parser/test_jd_parser.py",
    "Retriever": "Retriever/test_retriever.py",
    "LLM": "LLM/test_evidence.py",
    "Ranker": "Ranker/test_scoring.py",
}


def check_unit_tests(fast: bool, verbose: bool) -> None:
    header("3. unit tests")
    for name, path in SUITES.items():
        if not (ROOT / path).exists():
            record("tests", name, FAIL, f"{path} not found")
            continue
        if fast and name == "OCR":
            record("tests", name, SKIP, "--fast")
            continue

        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q", "--no-header",
             "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        dt = (time.perf_counter() - t0) * 1000
        stream = proc.stdout.strip() or proc.stderr.strip()
        tail = [ln for ln in stream.splitlines() if ln.strip()]
        summary = tail[-1] if tail else "no output"

        if proc.returncode == 0:
            record("tests", name, PASS, f"{summary}  {dt:.0f}ms")
        else:
            record("tests", name, FAIL, summary)
            if verbose:
                print(_c(proc.stdout[-3000:], "90"))


# --------------------------------------------------------------------------
# 4. integration — the join nothing else tests


JD_TEXT = """Senior Data Engineer

We are looking for an engineer to own our streaming ingestion platform.

Required: strong Python, production Kubernetes experience, and hands-on work
with Kafka at scale.
Nice to have: Terraform, and exposure to Go.
"""


def _mock_router(system: str, user: str) -> dict:
    """Stands in for GPT. Returns what a real model would plausibly return.

    Routes on the system prompt, then derives depth from *where* each skill
    appears in the excerpts — so the mock exercises the same code paths the
    real model would, including the grounding check, without a network call.
    """
    if "hiring requirements" in system or "job description" in system.lower():
        return {
            "role_title": "Senior Data Engineer",
            "mandatory_skills": [{"name": "Python", "category": "language"},
                                 {"name": "Kubernetes", "category": "cloud"},
                                 {"name": "Kafka", "category": "data"}],
            "preferred_skills": [{"name": "Terraform", "category": "cloud"},
                                 {"name": "Go", "category": "language"}],
            "min_years_experience": 5,
            "education": None,
            "responsibilities": ["Own the streaming ingestion platform"],
        }

    # evidence prompt: pull the skill list and the excerpts back out.
    # Chunks are multi-line, so excerpts must be split on the `[section]`
    # markers rather than line by line.
    import re

    skills = [m.group(1).strip()
              for m in re.finditer(r"^- (.+?) \((?:mandatory|preferred)\)$",
                                   user, re.MULTILINE)]
    tail = user.split("section it came from):", 1)[-1]
    excerpts = [(m.group(1), m.group(2).strip())
                for m in re.finditer(r"\[(\w+)\]\s*(.*?)(?=\n\[\w+\]|\Z)",
                                     tail, re.DOTALL)]

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
            # quote a real span so the grounding check in evidence.py passes
            idx = body.lower().index(skill.lower())
            evidence = body[max(0, idx - 30):idx + 40].strip()
            if depth in ("used", "strong"):
                break
        out.append({"skill": skill, "depth": depth, "evidence": evidence,
                    "section": None, "confidence": 0.9})
    return {"assessments": out}


def check_integration(verbose: bool) -> bool:
    header("4. integration (stage 1 -> 2 -> 3, offline)")

    from OCR import extract
    from Parser import MockProvider, parse_jd
    from Retriever import HashingEmbedder, HybridRetriever
    from LLM import assess_resume
    from Ranker import (estimate_experience, rank_candidates,
                        score_candidate)

    fixtures = ROOT / "OCR" / "fixtures"
    if not fixtures.exists() or not any(fixtures.glob("*.pdf")):
        print(_c("     generating fixtures...", "90"))
        subprocess.run([sys.executable, str(ROOT / "OCR" / "make_fixtures.py")],
                       capture_output=True, cwd=str(ROOT))
    paths = sorted(fixtures.glob("*.pdf")) + sorted(fixtures.glob("*.docx"))
    if not paths:
        record("integration", "fixtures", FAIL, "none generated")
        return False

    provider = MockProvider(_mock_router)
    embedder = HashingEmbedder()

    # --- JD parse (one call per batch, not per resume)
    req = parse_jd(JD_TEXT, provider)
    ok = bool(req.mandatory_skills) and bool(req.preferred_skills)
    record("integration", "parse_jd", PASS if ok else FAIL,
           f"{len(req.mandatory_skills)} mandatory / "
           f"{len(req.preferred_skills)} preferred")
    if not ok:
        return False

    # --- per resume: extract -> retrieve -> assess -> score
    scores, failures = [], []
    for p in paths:
        try:
            r = extract(p)
            if not r.ok:
                failures.append(f"{p.name}: {r.error or 'no text'}")
                continue
            ev = HybridRetriever(r.sections, embedder=embedder).retrieve_all(
                req, top_k=3)
            assessments, _ = assess_resume(req, ev, provider)
            scores.append(score_candidate(
                req, assessments, path=str(p),
                extraction_confidence=r.confidence,
                experience=estimate_experience(r.sections)))
        except Exception as exc:
            failures.append(f"{p.name}: {type(exc).__name__}: {exc}")

    record("integration", "extract -> retrieve -> assess -> score",
           PASS if not failures else FAIL,
           f"{len(scores)}/{len(paths)} resumes"
           + ("  " + "; ".join(failures) if failures else ""))
    if not scores:
        return False

    # --- contract assertions the per-module suites cannot make
    checks = [
        ("sections reach the retriever",
         all(isinstance(s, str) for s in extract(paths[0]).sections.values())),
        ("every JD skill is assessed",
         all(len(c.assessments) == len(req.all_skills) for c in scores)),
        ("scores are within 0-100",
         all(0.0 <= c.score <= 100.0 for c in scores)),
        ("extraction confidence propagates",
         all(0.0 <= c.extraction_confidence <= 1.0 for c in scores)),
        ("explanation is populated",
         all(c.explanation.strip() for c in scores)),
        ("output is JSON-serialisable",
         _json_ok(scores)),
        # A pipeline that scores every resume identically is broken but would
        # pass every check above. This is the one that catches that.
        ("experience evidence survives into the output",
         all(s.experience is not None and s.experience.evidence for s in scores)),
        ("years of experience are scored",
         all(any(c.label == "Years of experience" for c in s.components)
             for s in scores)),
        ("ranking discriminates between resumes",
         len(scores) < 2 or (max(c.score for c in scores)
                             - min(c.score for c in scores)) > 1.0),
    ]
    for label, passed in checks:
        record("integration", label, PASS if passed else FAIL)

    # --- rank
    ranked = rank_candidates(scores)
    monotonic = all(ranked[i].score >= ranked[i + 1].score
                    for i in range(len(ranked) - 1))
    ranks_ok = [c.rank for c in ranked] == list(range(1, len(ranked) + 1))
    record("integration", "rank_candidates",
           PASS if (monotonic and ranks_ok) else FAIL,
           f"{len(ranked)} ranked, descending" if monotonic else "not sorted")

    # --- format invariance: the SAME resume, put through four different
    # document pathologies, must land on the same score. This is the property
    # stage 1 exists to guarantee, and nothing else in the repo asserts it.
    by_name = {Path(c.path).name: c.score for c in scores}
    variants = ["two_column.pdf", "two_column_copy.pdf", "scanned.pdf",
                "junk_layer.pdf", "single_column.pdf"]
    present = {n: by_name[n] for n in variants if n in by_name}
    if len(present) >= 2:
        spread = max(present.values()) - min(present.values())
        record("integration", "format invariance (native/2-col/scan/junk)",
               PASS if spread <= 2.0 else FAIL,
               f"spread {spread:.1f} pts across {len(present)} variants")

    # --- duplicate detection: the same candidate applying twice under two
    # filenames must not occupy two ranking slots unnoticed.
    from OCR import extract_batch, find_duplicates
    dupes = find_duplicates(extract_batch([str(p) for p in paths]))
    record("integration", "find_duplicates",
           PASS if dupes else WARN,
           f"{len(dupes)} near-duplicate pair(s)" if dupes
           else "none found — expected two_column vs two_column_copy")

    # --- determinism: same inputs must give the same number, twice
    again = score_candidate(req, scores[0].assessments, path=scores[0].path,
                            extraction_confidence=scores[0].extraction_confidence,
                            experience=scores[0].experience)
    record("integration", "scoring is deterministic",
           PASS if again.score == scores[0].score else FAIL,
           f"{scores[0].score} == {again.score}")

    if verbose:
        print()
        for c in ranked:
            print(_c(f"     #{c.rank}  {c.score:5.1f}  {c.role_or_path()}", "90"))
            print(_c(f"           {c.summary}", "90"))

    return all(st is PASS for lay, _, st in results if lay == "integration")


def _json_ok(scores) -> bool:
    import json
    try:
        json.dumps([c.to_dict() for c in scores])
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 5. live API (opt-in)


def check_live() -> None:
    header("5. live OpenAI round-trip")
    if not os.environ.get("OPENAI_API_KEY"):
        record("live", "OPENAI_API_KEY", SKIP, "not set")
        return
    try:
        from Parser import OpenAIProvider, parse_jd
        req = parse_jd(JD_TEXT, OpenAIProvider(model="gpt-4o-mini"))
        names = {s.name.lower() for s in req.all_skills}
        hit = any(k in " ".join(names) for k in ("python", "kafka", "kubernetes"))
        record("live", "parse_jd via gpt-4o-mini", PASS if hit else FAIL,
               f"{len(req.all_skills)} skills: "
               + ", ".join(s.name for s in req.all_skills[:6]))
    except Exception as exc:
        record("live", "parse_jd via gpt-4o-mini", FAIL,
               f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="check.py",
        description="Verify every module in the resume screening pipeline.")
    ap.add_argument("--fast", action="store_true",
                    help="skip the OCR suite (rasterisation + OCR is slow)")
    ap.add_argument("--live", action="store_true",
                    help="also make one real OpenAI call")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="show pytest output on failure and the ranked table")
    args = ap.parse_args()

    t0 = time.perf_counter()
    print(_c("resume screening — module verification", "1"))
    print(_c(f"repo: {ROOT}", "90"))

    check_environment(args.fast)
    check_imports()
    check_unit_tests(args.fast, args.verbose)

    try:
        check_integration(args.verbose)
    except Exception as exc:
        record("integration", "integration harness", FAIL,
               f"{type(exc).__name__}: {exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()

    if args.live:
        check_live()

    failed = [n for _, n, st in results if st is FAIL]
    skipped = [n for _, n, st in results if st is SKIP]
    dt = time.perf_counter() - t0

    header("summary")
    print(f"  {len(results) - len(failed) - len(skipped)} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped   ({dt:.1f}s)")
    if failed:
        print(_c("  failed: " + ", ".join(failed), "31"))
        return 1
    print(_c("  all checks passed", "32"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())