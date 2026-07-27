# Design notes — resume text extraction

This is stage 1 of the resume screening system: documents in, structured
provenance-tagged text out. This note explains why it is built the way it is,
what it assumes, and what was traded away on purpose.

## The premise

Extraction quality caps everything downstream. The ranker never sees the
original PDF — it sees whatever this stage produces, and it has no independent
way to tell good extraction from bad. So the two failure modes are not equal. A
stage that extracts nothing is recoverable: the ranker sees empty text, assigns
low confidence, a human looks. A stage that extracts *plausible nonsense* — a
skills column fused into an experience column — is not recoverable, because
nothing downstream can tell it happened. The whole design follows from
preferring the first failure to the second: fail loudly, attach provenance to
everything, and never emit a clean-looking string you cannot stand behind.

## Decision 1 — PyMuPDF as the native engine, not PyPDF2

The starting point was a three-tier chain: pdfplumber → PyPDF2 → OCR. The middle
tier does nothing. Both pdfplumber and PyPDF2 read the same embedded text layer,
so when pdfplumber returns nothing PyPDF2 also returns nothing — it is a
fallback that cannot fall back.

PyMuPDF replaces it for a concrete reason, not novelty: `get_text("dict")`
returns per-block bounding boxes, font sizes and style flags. That geometry is
the raw material for column detection and heading detection. Without it, columns
and sections have to be reconstructed from a flat string after the fact, which
is strictly harder than reading them off positions that were right there.
PyMuPDF also renders pages in-process, which removes poppler as a system
dependency for the OCR path — one fewer thing to install wrong.

pdfplumber is kept for the one thing it does better than PyMuPDF: ruled-table
extraction.

## Decision 2 — an explainable quality gate, not `len(text) < 50`

The old OCR trigger was a length check. It fails open, and the failure is the
dangerous direction. A scanned resume exported from Canva or an ATS routinely
carries a short but real text layer — a watermark, a page footer, a broken
embedded OCR layer. That clears fifty characters, OCR never fires, and the
candidate is ranked on a watermark. (The test fixture `junk_layer.pdf`
reproduces exactly this: 113 characters of valid text sitting on top of an image
that holds the actual resume.)

The replacement scores text on six independent signals — density, encoding
artefacts, alphabetic ratio, single-character-token ratio, word plausibility,
and resume landmarks — and returns a verdict (`good` / `suspect` / `bad` /
`empty`) with each signal's contribution attached. Two things this buys beyond
correctness: the decision is inspectable (`quality.reasons` says *"very low text
density (113 chars/page) — likely scanned"* rather than a bare boolean), and the
`suspect` band gives the pipeline a way to say "this text exists but might be
junk" — the case the length check could not express. On a `suspect` page both
paths run and the better-scoring one wins, with native breaking ties because it
is exact where OCR is probabilistic.

The signals are deliberately language-agnostic and dictionary-free — vowel
presence and token-length sanity, not a word list — so the gate does not quietly
fail on a non-English resume.

## Decision 3 — route per page, not per document

A resume is not uniformly digital or scanned. The common mixed case is someone
who signs page 2, scans that page, and staples it back onto a digital document.
A document-level decision either OCRs the clean pages for nothing or misses the
scanned one. Routing per page costs nothing extra on clean documents and is the
only thing that handles the mixed case correctly.

## Decision 4 — OCR is a fallback, and cost is why

Measured on this machine: native extraction is ~5 ms/page; OCR at 300 DPI is
~3,200 ms/page — about 630× more expensive. On a batch of 500 resumes that is
the difference between a few seconds and half an hour. OCR therefore runs only
when the quality gate on the native text says it must. "OCR everything to be
safe" is the expensive wrong default; the gate is what lets the pipeline be both
safe and cheap.

## Decision 5 — one column algorithm, shared by both paths

Columns are the highest-value correctness problem, because the failure is
silent. Naive extraction of a two-column resume fuses the sidebar and the main
column at each shared y-coordinate:

```
Python, SQL, Docker      Senior Engineer, Acme Corp   2021-2023
```

This does not raise, does not warn, and reads fine in a log. An embedding model
then encodes the nonsense at face value.

The detector builds a horizontal ink-density profile (weighted by block height,
so a one-line heading does not count as much as a 40-line column), finds the
whitespace gutter, and validates it: both sides must span a real fraction of the
page's vertical extent, which distinguishes a true column boundary from the gap
before a right-aligned date. Blocks are then split into horizontal bands at
every full-width element and read column-major within each band — so full-width
headers and section rules are preserved rather than swallowed into one column.

The important architectural point: **this runs on both the native and OCR
paths.** Tesseract's own line grouping fuses columns exactly the way naive PDF
extraction does — a scan of a two-column resume produces `SKILLS EXPERIENCE` as
one line. So the OCR path discards tesseract's line hierarchy, keeps only its
(reliable) word boxes, and feeds them through the same gutter detection. One
implementation, and neither path can fuse columns.

Getting this right took four iterations, each a real bug: the right page margin
masquerading as the gutter (it is wider than the real one); an ink-volume
balance test rejecting a legitimately sparse sidebar; a single long email
address bridging the gutter and hiding it; and tesseract fusing the columns one
layer down. The fixes are documented at their call sites.

## Decision 6 — sections belong in the extractor

Section segmentation lives here, not in the ranker, because the evidence needed
to find headers — font size, boldness, block geometry — exists at extraction
time and is gone by the time you have a flat string. A header is recognised only
when it both matches a known section name *and* looks like a heading (uppercase,
bold, or larger than body text), so the word "skills" inside a sentence does not
open a section.

This is load-bearing downstream. "Kubernetes" in a skills laundry list is weak
evidence; "Kubernetes" inside a dated experience bullet is strong evidence. A
ranker that cannot tell them apart rewards keyword stuffing. Every block carries
its section tag into the JSON output so the scoring stage can weight by it.

## Assumptions

- Resumes are 1–3 pages; beyond 12 pages the pipeline processes the first 12 and
  warns (likely a portfolio, not a resume).
- At most two columns. Three-plus-column academic CVs get the dominant split
  only.
- Latin script by default; other scripts need the tesseract language pack and
  `--lang`.
- A resume has recognisable landmarks — contact details and section headers.
  Text lacking both is flagged as possibly-not-a-resume rather than trusted.

## Trade-offs made deliberately

- **300 DPI default for OCR.** The cost/accuracy knee for 9–10pt body text.
  Honest caveat: the synthetic fixtures are clean renders, where 150 DPI scored
  as well as 300 (94.9 vs 94.7 confidence). The 300 default is a judgement about
  *real* noisy scans — phone photos, faxed pages — not something these fixtures
  prove. It is a CLI flag precisely because the right value is document-dependent.
- **Table text is flattened into the stream** as `cell | cell | cell` in
  addition to the structured rows. Complex merged-cell layouts lose their
  spanning structure. The alternative — keeping tables only as structured
  objects — would drop skills out of the text a keyword search sees. Flattening
  serves the downstream ranker better; the structured rows remain available for
  anything that wants them.
- **Threads, not processes, for batching.** The heavy work (tesseract, MuPDF)
  releases the GIL, so threads get real parallelism while keeping memory flat
  and avoiding pickling results across process boundaries.
- **No layout ML model.** A geometric gutter detector is inspectable, fast, and
  has no model to ship or version. It cannot handle arbitrarily complex layouts
  the way a trained model could — but resume layouts are a narrow domain, and
  every decision this detector makes can be explained in one sentence, which
  matters more here than raw ceiling.

## What feeds the ranking stage

The `confidence` field (0–1) is the one number the ranker should gate on: it
folds the quality score together with mean OCR confidence, so a candidate whose
resume extracted at 46% confidence can be held back from a confident low rank
and routed to review instead. The per-block `section`, `column`, `in_table` and
`confidence` fields are the evidence-weighting inputs. The near-duplicate
fingerprint catches the same candidate applying twice under two filenames before
they occupy two slots in the ranking.
