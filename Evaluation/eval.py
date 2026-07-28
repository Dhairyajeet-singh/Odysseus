#!/usr/bin/env python3
"""eval.py — measure ranking quality against labelled ground truth.

    python eval.py Results/ai-ml-eng-entry-level_ranking.json
    python eval.py Results/new.json --compare Results/old.json
    python eval.py Results/run.json --json metrics.json

Reads a ranking produced by `main.py`; it makes no API calls, so a run can be
evaluated as many times as you like for free.

Why this exists
---------------
"Ranking quality" is the first evaluation criterion of the assignment, and unit
tests cannot speak to it. 103 passing tests prove each component behaves as
specified; none of them prove the ordering is any good. This measures that.

What is being measured
----------------------
The pipeline is judged on ORDER, not on absolute scores. A run that gave every
candidate half marks but ranked them all correctly would score perfectly here,
and it should -- the score scale is a presentation choice, the ordering is the
product. Metrics:

  Spearman rho / Kendall tau   rank correlation with the labelled tiers
  NDCG@k                       ordering quality, weighted toward the top
  Precision@k                  fraction of the shortlist actually qualified
  separation                   gap between worst qualified and best unqualified
  inversions                   specific pairs ordered wrongly, named

Ties in the ground truth are expected -- five candidates share grade 2 and any
order among them is equally correct. Both correlation measures handle ties
properly (average ranks for Spearman, tau-b for Kendall), so the pipeline is
never penalised for a choice the labels do not constrain.

Correlations are computed here rather than pulled from scipy: they are twenty
lines, and adding a dependency for them would be a poor trade.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent
GRADE_NAME = {4: "perfect", 3: "close", 2: "good", 1: "decent", 0: "poor"}
QUALIFIED = 3          # grade >= this counts as a candidate worth interviewing
IN_FIELD = 1           # grade >= this means the resume is at least in the field


# ---------------------------------------------------------------------------
# statistics


def _rank_avg(x: np.ndarray) -> np.ndarray:
    """Ranks with ties averaged — the tie handling Spearman requires."""
    order = np.argsort(-x, kind="mergesort")
    ranks = np.empty(len(x), float)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = _rank_avg(a), _rank_avg(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    denom = float(np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))
    return float((ra * rb).sum() / denom) if denom else 0.0


def kendall_tau_b(a: np.ndarray, b: np.ndarray) -> float:
    """tau-b: the variant that corrects for ties on either side."""
    n = len(a)
    conc = disc = ta = tb = 0
    for i in range(n):
        for j in range(i + 1, n):
            da, db = a[i] - a[j], b[i] - b[j]
            if da == 0 and db == 0:
                continue          # tied on both: excluded from tau-b entirely
            elif da == 0:
                ta += 1
            elif db == 0:
                tb += 1
            elif (da > 0) == (db > 0):
                conc += 1
            else:
                disc += 1
    denom = np.sqrt((conc + disc + ta) * (conc + disc + tb))
    return float((conc - disc) / denom) if denom else 0.0


def _dcg(rel: Sequence[float]) -> float:
    rel = np.asarray(rel, float)
    return float(np.sum((2 ** rel - 1) / np.log2(np.arange(2, len(rel) + 2))))


def ndcg(rel_in_rank_order: Sequence[float], k: Optional[int] = None) -> float:
    rel = np.asarray(rel_in_rank_order, float)
    got = rel[:k] if k else rel
    ideal = np.sort(rel)[::-1][:k] if k else np.sort(rel)[::-1]
    d = _dcg(ideal)
    return _dcg(got) / d if d else 0.0


# ---------------------------------------------------------------------------
# loading


def stem(path: str) -> str:
    """Basename without extension, tolerating Windows separators in the JSON."""
    return ntpath.splitext(ntpath.basename(path.replace("/", "\\")))[0]


def load_ranking(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("shortlist", [])
    if not rows:
        raise SystemExit(f"error: no shortlist in {path}")
    return sorted(rows, key=lambda c: c["rank"])


def load_labels(path: Path) -> Tuple[Dict[str, int], Dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["grades"], data.get("thresholds", {})


# ---------------------------------------------------------------------------
# evaluation


def evaluate(rows: List[dict], grades: Dict[str, int]) -> dict:
    labelled, unlabelled = [], []
    for c in rows:
        name = stem(c["path"])
        (labelled if name in grades else unlabelled).append((name, c))

    if len(labelled) < 3:
        raise SystemExit("error: fewer than 3 labelled candidates matched — "
                         "check that eval_labels.json names match the filenames")

    names = [n for n, _ in labelled]
    scores = np.array([c["score"] for _, c in labelled], float)
    rel = np.array([grades[n] for n in names], float)

    # Separation asks one specific question: does every in-field candidate
    # outscore every out-of-field one? Overlap BETWEEN adjacent tiers is normal
    # and is reported through `inversions` instead -- a "good" backend engineer
    # legitimately beating a weak "close" match is a judgement call, not a bug.
    # A nurse outscoring a junior ML engineer is a bug.
    in_field = scores[rel >= IN_FIELD]
    off_field = scores[rel < IN_FIELD]
    separation = (float(in_field.min() - off_field.max())
                  if len(in_field) and len(off_field) else float("nan"))

    # Pairs the pipeline ordered against the labels. Equal grades are not
    # inversions — the labels express no preference within a tier.
    inversions = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if rel[j] > rel[i] and scores[j] < scores[i]:
                inversions.append((names[i], int(rel[i]), scores[i],
                                   names[j], int(rel[j]), scores[j]))

    by_tier = {}
    for g in sorted(GRADE_NAME, reverse=True):
        vals = scores[rel == g]
        if len(vals):
            ranks = [k + 1 for k, r in enumerate(rel) if r == g]
            by_tier[GRADE_NAME[g]] = {
                "n": int(len(vals)), "mean": round(float(vals.mean()), 1),
                "min": round(float(vals.min()), 1),
                "max": round(float(vals.max()), 1),
                "ranks": [min(ranks), max(ranks)],
            }

    top = rel[:5]
    return {
        "n_labelled": len(labelled),
        "n_unlabelled": len(unlabelled),
        "spearman": round(spearman(scores, rel), 3),
        "kendall_tau": round(kendall_tau_b(scores, rel), 3),
        "ndcg_at_3": round(ndcg(rel, 3), 3),
        "ndcg_at_5": round(ndcg(rel, 5), 3),
        "ndcg_at_10": round(ndcg(rel, 10), 3),
        "ndcg_all": round(ndcg(rel), 3),
        "precision_at_5_qualified": round(float(np.mean(top >= QUALIFIED)), 2),
        "precision_at_5_relevant": round(float(np.mean(top >= 2)), 2),
        "separation": round(separation, 1),
        "n_inversions": len(inversions),
        "inversions": inversions,
        "by_tier": by_tier,
        "unlabelled": [(n, c["rank"], c["score"]) for n, c in unlabelled],
    }


# ---------------------------------------------------------------------------
# reporting


BAR = "─" * 74
HEADLINE = [("spearman", "Spearman rho", "rank correlation with the labels"),
            ("kendall_tau", "Kendall tau-b", "same, tie-corrected"),
            ("ndcg_at_3", "NDCG@3", "is the top of the list right"),
            ("ndcg_at_5", "NDCG@5", "is the shortlist right"),
            ("ndcg_all", "NDCG (all)", "whole-ordering quality")]


def report(m: dict, thresholds: Dict[str, float], verbose: bool) -> bool:
    print(f"\n{BAR}\nRANKING QUALITY   {m['n_labelled']} labelled candidates")
    print(BAR)

    for key, label, gloss in HEADLINE:
        limit = thresholds.get(key)
        mark = "" if limit is None else ("  ok" if m[key] >= limit else "  BELOW")
        lim = "" if limit is None else f"  (min {limit})"
        print(f"  {label:16} {m[key]:6.3f}{lim}{mark}")
        if verbose:
            print(f"                   {gloss}")

    print(f"\n  Precision@5      {m['precision_at_5_qualified']:6.2f}   "
          f"of the top 5, fraction genuinely qualified")
    print(f"  Precision@5      {m['precision_at_5_relevant']:6.2f}   "
          f"... fraction at least relevant")

    sep_limit = thresholds.get("separation")
    sep_mark = "" if sep_limit is None else (
        "  ok" if m["separation"] >= sep_limit else "  BELOW")
    print(f"  Separation       {m['separation']:6.1f}   points between the worst "
          f"in-field candidate\n                            and the best "
          f"off-field one{sep_mark}")

    print(f"\n{BAR}\nBY TIER\n{BAR}")
    print(f"  {'tier':9} {'n':>2}  {'mean':>6} {'range':>12}  ranks")
    for tier, s in m["by_tier"].items():
        print(f"  {tier:9} {s['n']:2d}  {s['mean']:6.1f} "
              f"{s['min']:5.1f}-{s['max']:<5.1f}  #{s['ranks'][0]}-#{s['ranks'][1]}")

    if m["unlabelled"]:
        print(f"\n  not labelled (excluded from every metric above):")
        for name, rank, score in m["unlabelled"]:
            print(f"    #{rank:<3} {score:5.1f}  {name}")

    if m["inversions"]:
        print(f"\n{BAR}\nINVERSIONS — {m['n_inversions']} pair(s) ordered against "
              f"the labels\n{BAR}")
        for a, ga, sa, b, gb, sb in m["inversions"][:12]:
            print(f"  {b} ({GRADE_NAME[gb]}, {sb:.0f}) should outrank "
                  f"{a} ({GRADE_NAME[ga]}, {sa:.0f})")
        if m["n_inversions"] > 12:
            print(f"  ... and {m['n_inversions'] - 12} more")

    failed = [k for k, v in thresholds.items() if k in m and m[k] < v]
    print(f"\n{BAR}")
    if failed:
        print(f"  FAIL — below threshold: {', '.join(failed)}")
    else:
        print(f"  PASS — all {len(thresholds)} thresholds met")
    print(BAR)
    return not failed


def compare(now: dict, before: dict) -> None:
    print(f"\n{BAR}\nCOMPARED WITH BASELINE\n{BAR}")
    keys = ["spearman", "kendall_tau", "ndcg_at_3", "ndcg_at_5", "ndcg_all",
            "precision_at_5_qualified", "separation", "n_inversions"]
    worse = []
    for k in keys:
        a, b = before.get(k), now.get(k)
        if a is None or b is None:
            continue
        d = b - a
        # more inversions is worse; for every other metric, higher is better
        bad = d > 0 if k == "n_inversions" else d < 0
        mark = "  WORSE" if bad and abs(d) > 1e-9 else ""
        if mark:
            worse.append(k)
        print(f"  {k:26} {a:8.3f} -> {b:8.3f}   {d:+.3f}{mark}")
    print(BAR)
    print("  regression detected" if worse else "  no regression")
    print(BAR)


# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="eval.py",
        description="Measure ranking quality against labelled ground truth.")
    ap.add_argument("ranking", help="a *_ranking.json written by main.py")
    ap.add_argument("--labels", default=str(ROOT / "eval_labels.json"))
    ap.add_argument("--compare", help="an earlier ranking.json, to detect "
                                      "regressions between runs")
    ap.add_argument("--json", help="write the metrics to this file")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    grades, thresholds = load_labels(Path(args.labels))
    metrics = evaluate(load_ranking(Path(args.ranking)), grades)
    ok = report(metrics, thresholds, args.verbose)

    if args.compare:
        compare(metrics, evaluate(load_ranking(Path(args.compare)), grades))

    if args.json:
        Path(args.json).write_text(json.dumps(metrics, indent=2),
                                   encoding="utf-8")
        print(f"written: {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())