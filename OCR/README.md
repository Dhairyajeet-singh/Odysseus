# resume-extract

Layout-aware text extraction for resumes (PDF and DOCX), with a quality-gated
OCR fallback. This is stage 1 of the resume screening & ranking system: it turns
arbitrary candidate documents into structured, provenance-tagged text that the
matching and scoring stages can rely on.

Extraction quality caps everything downstream. A ranker cannot recover from a
resume whose skills column was fused into its experience column, and it has no
way to know that happened — so this stage is built to fail loudly rather than
quietly.

## What it handles

| Case | Behaviour |
|---|---|
| Digital PDF | Text layer via PyMuPDF, with block geometry and typography |
| Two-column / sidebar layouts | Gutter detected from ink profile, blocks re-ordered column-major |
| Ruled tables | Structured rows via pdfplumber, without double-counting into the text stream |
| Scanned / image-only PDF | Rasterised and OCR'd, with per-word confidence |
| PDF with a junk text layer | Detected by quality scoring and re-OCR'd |
| Mixed digital + scanned pages | Routed **per page**, not per document |
| DOCX | Body, tables, text boxes, headers/footers and hyperlink targets |
| Rotated scans | Corrected via tesseract OSD when available |
| Wrong file extension | Identified by magic bytes, not filename |
| Corrupt/encrypted file | Returns an error object; never breaks a batch |

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# system dependency for the OCR path only
sudo apt-get install -y tesseract-ocr        # Debian/Ubuntu
# brew install tesseract                     # macOS
```

No poppler required — rendering is done in-process by PyMuPDF.

Verify:

```bash
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

## Use

```bash
# one file
python -m resume_extract.cli resume.pdf

# a folder, writing .txt + .json per document
python -m resume_extract.cli ./resumes -o ./extracted

# flag candidates who applied twice under different filenames
python -m resume_extract.cli ./resumes --duplicates

# debugging: force a path, change OCR resolution
python -m resume_extract.cli resume.pdf --force ocr --dpi 400
```

Example output:

```
OK    priya_cv.pdf  [native] conf=1.00 chars=985 cols=2 sections=header,skills,education,experience,projects 218ms
        ! page 1: two-column layout detected (gutter x=148-177pt) — blocks reordered column-major
OK    scan_003.pdf  [ocr] conf=0.98 chars=976 cols=2 sections=header,skills,education,experience 8553ms
        ! page 1: no text layer but images present — scanned page
        ! page 1: OCR ran — native text layer unusable
```

### Library

```python
from resume_extract import extract, extract_batch, find_duplicates, Config

r = extract("resume.pdf")

r.text                  # reading-order text, blank lines preserved
r.sections["skills"]    # {"header","summary","experience","education","skills",...}
r.blocks                # per-block: page, bbox, column, section, source, OCR confidence
r.tables                # structured rows
r.links                 # hyperlink targets (the LinkedIn URL behind "LinkedIn")
r.confidence            # 0-1, gate on this before trusting a low rank
r.quality.reasons       # why the score is what it is, in plain English
r.pages[0].method       # which path ran, per page
r.warnings              # everything the pipeline noticed

results = extract_batch(paths, Config(workers=8))
find_duplicates(results)   # [(path_a, path_b, hamming_distance)]
```

Every extraction returns a result object. Failures populate `r.error` rather
than raising, so one bad file cannot end a batch of five hundred.

## Output schema

`to_dict()` produces JSON with `text`, `sections`, `blocks`, `tables`, `links`,
`quality` (score, verdict and the individual signals with their penalties),
`pages` (per-page method, column count, gutter position, OCR confidence and
segmentation mode), `confidence`, both fingerprints, `warnings` and `timings_ms`.

The per-block `section`, `column` and `confidence` fields are what let the
scoring stage weight evidence: a skill inside an experience bullet is stronger
evidence than the same token in a skills list, and a skill read at 46% OCR
confidence should not be treated like one read from a clean text layer.

## Tests

```bash
python tests/make_fixtures.py     # generates the fixture documents
python -m pytest tests/ -v
```

17 tests, one per failure mode. The fixtures are generated rather than committed
so there are no real resumes in the repository — they synthesise a two-column
layout, a ruled skills table, an image-only scan, a scan carrying a decoy text
layer, and a DOCX with a text box, table, header and hidden hyperlink.

## Known limitations

- Three or more columns are not detected; the gutter search finds the single
  dominant split. Rare in resumes, common in academic CVs.
- Non-Latin scripts need the matching tesseract language pack and `--lang`.
- Table cell text is emitted as flattened rows in the text stream; complex
  merged-cell layouts lose their spanning structure.
- Reading order within a page band assumes left-to-right column order.
- An image-only DOCX is reported as a warning rather than being auto-converted.

See `DESIGN.md` for the reasoning behind the routing policy and the trade-offs
that were made deliberately.
