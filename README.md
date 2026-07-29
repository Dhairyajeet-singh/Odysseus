# Odysseus

**Resume screening and ranking with explainable scores.**

Give it one job description and a folder of resumes. It reads every file — native
PDF, two-column layout, scanned image, or DOCX — works out how well each
candidate matches, and produces a ranked list where every score breaks down into
the evidence that produced it.

#**[Deployed Version](odysseus-production-f505.up.railway.app)**
```
#1  93/100   aarav_mehta.pdf
    Strong match. 5/6 required skills demonstrated (5 strongly). 5/5 preferred demonstrated.
    matched : Python, PyTorch, Computer vision, FastAPI, Docker, SQL, Azure, LangChain
    gaps    : Python (listed only, not demonstrated)
      Mandatory skills        63.0 / 70.0   5 demonstrated, 1 listed-only, 0 missing of 6
      Preferred skills        30.0 / 30.0   5 demonstrated, 0 listed-only, 0 missing of 5
      Years of experience     15.0 / 15.0   6.9 years, meets the 5-year minimum
```

Available three ways: a **web interface**, a **command-line tool**, and an
**Excel export** for handing results to someone who will never install Python.

---

## Try it without setting anything up

The repository ships with sample data so you can run it the moment you clone it:

| folder | contents |
|---|---|
| `JD/` | a sample job description |
| `Resume/` | 21 sample resumes — 20 synthetic across five quality tiers, plus one real one |

These stand in for real postings and applications, and they exist so the
pipeline can be demonstrated and measured without anyone's actual resume being
committed to a public repository. **Replace them with your own** — drop your
files into those folders, or point the tool anywhere else:

```bash
python main.py --jd path/to/your_jd.txt --resumes path/to/your_resumes/
```

Nothing depends on the sample files except `Evaluation/eval_labels.json`, which
grades those twenty synthetic resumes for the ranking-quality metrics below.
Swap the resumes and those particular numbers stop applying — the pipeline
itself is unaffected.

There is also a **[deployed version](odysseus-production-f505.up.railway.app)** if you would
rather click than clone.

---

## The one idea worth knowing

**The language model never produces the score.**

It is asked one question per skill — *how deeply does this resume evidence
this?* — and answers with a label and a quotation:

```json
{"skill": "Kubernetes", "depth": "strong",
 "evidence": "operated a payments service on AWS across three regions"}
```

Four labels, fixed weights: `none` 0.0, `mentioned` 0.4, `used` 0.8, `strong`
1.0. The 0–100 is arithmetic over those weights.

Asking a model for a number directly gives you a figure that is not
reproducible, not comparable between candidates scored in separate calls, and
impossible to explain to someone you rejected. Splitting the work this way puts
each half where it belongs: judging whether a bullet demonstrates depth or
merely lists a keyword is a language problem; turning judgements into a ranking
is arithmetic. Everything after the judgement is deterministic and tested.

Full reasoning in [DESIGN.md](DESIGN.md).

---

## Quick start

Requires **Python 3.10+**, and **Node 18+** for the web interface.

```bash
git clone https://github.com/Dhairyajeet-singh/Odysseus
cd Odysseus

python -m venv .venv
source .venv/bin/activate            # Windows:  .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Create `.env` in the project root:

```
OPENAI_API_KEY=sk-...
```

Verify the install:

```bash
python check.py
```

Dependencies, imports, all test suites, and a full offline run end to end.
Expect **72 tests passing** and every check green.

### Run the web interface

Two terminals.

```bash
# 1 — backend
uvicorn app:app --reload --port 8000

# 2 — frontend
cd Frontend
npm install
npm run dev
```

Open **http://localhost:3000**. Paste a job description, drag in resumes, and
watch the pipeline log its way through them.

Check `http://localhost:8000/api/health` first if anything looks wrong — you
want `"openaiKeyConfigured": true`. If it is false, `.env` is not at the repo
root.

### Run the command line

```bash
python main.py --jd JD/AI_Engineer_entry_level_jd.txt --resumes Resume/
```

### Single-process deployment

```bash
cd Frontend && npm run build && cd ..
uvicorn app:app --port 8000
```

FastAPI now serves the built frontend itself — one process, one port.

---

## Tesseract (optional)

Only needed for the OCR fallback: scanned PDFs, and pages whose text layer is
junk. Native PDFs and DOCX work without it.

| | |
|---|---|
| Windows | [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) — tick **Add to PATH**, then restart the shell |
| macOS | `brew install tesseract` |
| Debian/Ubuntu | `sudo apt-get install tesseract-ocr` |

```bash
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

No poppler required — PyMuPDF rasterises in-process.

---

## Usage

### Command line

```bash
python main.py --jd <jd> --resumes <folder> [options]
```

`--jd` takes a path or the text itself, and reads a PDF if the JD arrived as
one. `--resumes` takes a folder or a single file.

| flag | effect |
|---|---|
| `--out FILE` | also write one combined JSON here |
| `--results-dir DIR` | somewhere other than `Results/` |
| `--excel-dir DIR` | somewhere other than `Excel/Excel_Outputs/` |
| `--excel-name F` | workbook filename (default `rankings.xlsx`) |
| `--no-excel` | skip the spreadsheet |
| `--no-store` | console only |
| `--top N` | print only the top N |
| `--detail` | show the quoted evidence behind each skill judgement |
| `--workers N` | resumes screened in parallel (default 8) |
| `--top-k N` | chunks retrieved per skill (default 3) |
| `--model NAME` | OpenAI model (default `gpt-4o-mini`) |
| `--offline` | stub model, no key, no network — checks the plumbing |
| `--env-file P` | a `.env` somewhere else |
| `-q` | quiet |

Run `--offline` once first to confirm your folder parses, then drop the flag.

Output lands in `Results/`: one JSON per candidate named
`<jd>_<resume>_eval.json`, plus `<jd>_ranking.json` with the full ordering. A
spreadsheet is then written to `Excel/Excel_Outputs/rankings.xlsx`.

### Web API

The frontend is a client of this; it is also usable directly. Interactive docs
at `http://localhost:8000/docs`.

| | |
|---|---|
| `POST /api/jobs` | multipart: `resumes[]` plus `jd_text` or `jd_file` → `202 {jobId}` |
| `GET /api/jobs/{id}` | status, progress, logs, result |
| `GET /api/jobs/{id}/excel` | the workbook for that run |
| `POST /api/jobs/{id}/cancel` | stop an in-flight run |
| `DELETE /api/jobs/{id}` | discard the run and its uploaded files |
| `GET /api/health` | liveness, and whether a key is configured |

Screening runs as a background job rather than a held-open request: two hundred
resumes takes minutes, which no browser will wait through. `POST` returns
immediately; the client polls for progress. Uploaded files live in a temp
directory that is removed on `DELETE`, on eviction after an hour, or when the
job cap is reached — resumes are personal data and should not linger.

### Spreadsheet export

```bash
python Excel/export_excel.py Results/                     # -> rankings.xlsx
python Excel/export_excel.py Results/ --out shortlist.xlsx
```

One sheet per job description plus a Summary sheet, with frozen panes,
autofilter, and a colour scale down the Score column. Columns:

```
Resume | JD | Score | Rank | Matched Skills | Missing Skills | Mandatory Skills |
Preferred Skills | Assessment | Explanation | Summary | Experience | Flags |
Extraction Conf.
```

`Assessment` carries the depth judgement *and* the quoted evidence per skill, so
a hiring manager questioning a score can answer it without leaving the cell.

It reads the JSON `main.py` already wrote, so it makes no API calls and can be
re-run freely — including on runs from last week.

### Measuring ranking quality

Unit tests prove each component behaves as specified. They say nothing about
whether the *ordering* is any good, so that is measured separately against
labelled ground truth in `Evaluation/eval_labels.json`.

```bash
python Evaluation/eval.py Results/ai-ml-eng-entry-level_ranking.json
python Evaluation/eval.py Results/new.json --compare Results/old.json
```

---

## Results

Twenty synthetic resumes across five relevance tiers, graded 0–4 when they were
written rather than fitted to output.

```
Spearman rho      0.913  (min 0.8)   ok
Kendall tau-b     0.822
NDCG@3            1.000
NDCG@5            0.949  (min 0.85)  ok
NDCG (all)        0.988  (min 0.9)   ok
Precision@5        0.80
Separation        18.7                ok

  tier       n    mean        range   ranks
  perfect    2    91.2  89.4-93.0   #1-#2
  close      3    58.7  47.1-68.1   #3-#6
  good       5    34.4  23.3-63.3   #4-#12
  decent     5    25.1  18.7-36.5   #7-#15
  poor       5     0.0   0.0-0.0    #16-#20

  PASS — all 4 thresholds met
```

Ordering is what is measured, not scores — a run that halved every score but
kept the order would pass, and should. Ties in the ground truth are respected:
five candidates share a grade, and any order among them is equally correct.

The nine reported inversions all have one cause, and it is the labels rather
than the system. Every one is a deployment-skilled candidate outranking an
ML-depth candidate; the JD asks for 4 ML skills and 7 general engineering ones,
so the pipeline is right and the tier labels encode an assumption the JD does
not make. Discussed in [DESIGN.md](DESIGN.md).

**Format invariance:** the same resume as a clean single-column PDF, a
two-column layout, a rasterised scan, and a scan carrying a decoy text layer
scores within **0.0 points** across all four. That is the property the
extraction stage exists to provide, and `check.py` asserts it on every run.

---

## Cost

Measured, per resume, for a JD with 12 skills:

| | per run |
|---|---|
| LLM — JD parsing | 1, for the whole batch |
| LLM — evidence | 1 per resume |
| Embeddings | 13 per resume (1 chunk batch + 1 per skill) |

Screening 50 resumes is **51 LLM calls**. The JD is parsed once rather than once
per resume, which is where the saving comes from. Embeddings are not yet cached
— see limitations.

---

## Architecture

```
JD      -> parse (1 LLM call per run)  -> Requirements
resume  -> extract -> chunk -> retrieve -> judge (1 LLM call) -> score -> rank
```

**Extraction** (`OCR/`) — layout-aware PDF and DOCX reading. A six-signal
quality gate replaces `len(text) < 50`, catching the case that motivates it:
scanned pages carrying a decoy text layer that passes a length check and fails
everything else. OCR is decided page by page, not per document. Two-column
layouts are found by ink-profile analysis of the gutter. Headings are identified
by font size and boldness, then normalised — section provenance matters, because
the same word means different things in a skills list and an experience bullet.

**Retrieval** (`Retriever/`) — BM25 and embeddings fused 50/50, over
bullet-level chunks of 80–320 characters. They fail in opposite directions:
lexical search cannot tell that "AWS" and "Amazon Web Services" are the same
thing; semantic search returns something adjacent but wrong when the exact token
sits three lines away. No vector database — at 200 resumes × ~30 chunks that is
6,000 vectors, a NumPy matmul in single-digit milliseconds. The documented
switchover point is 50,000 chunks.

**Judgement** (`LLM/`) — one call per resume over the union of retrieved chunks,
not one per skill. Every quotation the model returns is checked against the text
actually supplied to it; if it does not appear, the assessment is flagged. A
model that invents a plausible bullet is the most dangerous failure mode here,
because the output looks exactly like a correct one.

**Scoring** (`Ranker/`) — 70 points from mandatory skills, 30 from preferred,
with 15 carved out for experience when the JD states a minimum. A missing
mandatory skill flags rather than disqualifies: in screening, a false negative
is invisible and permanent while a false positive costs someone fifteen minutes.
Experience is parsed deterministically from date ranges, with overlapping roles
merged and education excluded. A resume with no readable dates yields *unknown*,
never zero — zero is a claim about the candidate, unknown is a fact about our
parsing.

Skill normalisation happens in two layers. *Aliases* are other names for one
thing ("JS" for JavaScript). *Alternatives* are different technologies that each
satisfy one requirement — "PyTorch or TensorFlow" is one hurdle, not two.

---

## Providers

Backends sit behind two interfaces, `LLMProvider.complete_json` and
`Embedder.embed`. Nothing above `Parser/providers.py` knows which is in use.

| | implemented | verified end to end |
|---|---|---|
| OpenAI | yes | **yes** |
| Anthropic | yes | not yet |
| Mock / Hashing | yes | yes (used throughout the tests) |

```python
from Parser import get_provider
provider = get_provider("anthropic", model="claude-sonnet-4-6")
```

Anthropic needs `pip install anthropic` and `ANTHROPIC_API_KEY`. It is written
against the same interface but has not been exercised against a live key.

---

## Project layout

```
OCR/            documents -> structured, provenance-tagged text
Parser/         JD -> Requirements; the shared schema; LLM providers
Retriever/      hybrid BM25 + embedding retrieval over resume chunks
LLM/            the judgement step: depth labels with grounding checks
Ranker/         deterministic scoring, experience estimation, ranking

Backend/        background job runner for the web API
Frontend/       React 19 + Vite + Tailwind interface
Excel/          spreadsheet export -> Excel/Excel_Outputs/
Evaluation/     ranking quality against labelled ground truth

JD/             sample job descriptions
Resume/         sample resumes (20 synthetic + 1 real)
Results/        per-candidate and per-JD JSON, written by main.py

app.py          FastAPI application
main.py         the CLI pipeline, end to end
check.py        installation and integration verification
```

Dependencies run one way — `Parser` ← `Retriever` ← `LLM` ← `Ranker` — with no
cycles. `Parser/schema.py` is the shared vocabulary and imports from nothing.
The two packages holding the scoring logic have no third-party dependencies at
all.

```bash
python -m pytest -q              # 72 tests
python -m pytest Ranker/ -q      # one package
```

---

## Known limitations

Stated plainly, because a reviewer will find them anyway.

- **Duplicate detection is not wired into ranking.** Exact and near-duplicate
  fingerprints are computed in `OCR/`, but `rank_candidates` does not consume
  them, so a candidate applying twice occupies two slots. The detection half
  works; the acting half is a small patch away.
- **Embeddings are uncached.** Each skill query is re-embedded per resume, and
  each resume's chunks per JD. Measured at 1,300 calls where 32 would do across
  5 JDs × 20 resumes. A text-keyed cache is the largest remaining efficiency
  win.
- **`Python` is systematically under-credited.** It reads as *listed only* for
  most candidates, because bullets say "trained a PyTorch model" rather than
  naming the language. Not wrong, but the most universal requirement
  contributes little discrimination.
- **Seniority is a floor, not a band.** A JD saying "0–2 years" is read as a
  minimum, so an overqualified candidate is not screened out. Deliberate, but it
  means the system cannot express "we want someone early in their career."
- **JD parsing varies between runs.** The same JD occasionally yields a
  different skill count, which shifts every candidate's denominator. Caching the
  parsed JD would pin it.
- **Recency is not modelled.** Kubernetes used heavily in 2019 and not since
  scores the same as Kubernetes used last month.
- **Jobs live in memory.** A backend restart loses in-flight runs. For a
  single-process deployment that is the right amount of machinery.
- **The evaluation set is synthetic and small.** Twenty resumes, written by the
  same person who wrote the pipeline. Labels are honest, but the documents are
  cleaner and less ambiguous than real ones, and real-world numbers would be
  lower.

---

## Privacy

`Results/` and `Excel/Excel_Outputs/` hold candidate names, contact details, and
employment history. Both are gitignored. Uploads through the web interface are
written to a temp directory and deleted when the job is discarded or evicted.
Nothing is sent anywhere except the configured LLM provider.

---

## Documentation

- [DESIGN.md](DESIGN.md) — design decisions, assumptions, and trade-offs
- [OCR/DESIGN.md](OCR/DESIGN.md) — the extraction stage in depth, including the
  four column-detection approaches that were tried and discarded
