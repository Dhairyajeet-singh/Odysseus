"""Regression tests: one per failure mode the old pipeline had.

Run:  python -m pytest tests/ -v
Fixtures are generated on demand by tests/make_fixtures.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resume_extract import Config, Method, Verdict, extract, extract_batch, find_duplicates
from resume_extract.pipeline import sniff_format
from resume_extract.types import DocFormat

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (FIX / "two_column.pdf").exists():
        subprocess.run([sys.executable, str(Path(__file__).parent / "make_fixtures.py")],
                       check=True)
    return FIX


# --------------------------------------------------------------------------
# 1. two-column fusion — the silent corruption


def test_two_column_lines_are_not_fused():
    """Sidebar and main column must never share a line.

    The old pipeline produced 'Python Senior Data Engineer, Acme Corp'. It never
    raised, and the output looked plausible in a log — which is what made it
    dangerous.
    """
    r = extract(FIX / "two_column.pdf")
    for fused in ("Python Senior Data Engineer",
                  "SKILLS EXPERIENCE",
                  "CGPA 8.7 / 10 Owned data quality"):
        assert fused not in r.text, f"columns fused: {fused!r}"


def test_two_column_is_detected():
    r = extract(FIX / "two_column.pdf")
    assert r.pages[0].n_columns == 2
    assert r.pages[0].gutter is not None


def test_two_column_reading_order_keeps_columns_contiguous():
    """The whole sidebar must precede the whole main column."""
    r = extract(FIX / "two_column.pdf")
    t = r.text
    assert t.index("Terraform") < t.index("Senior Data Engineer")
    assert t.index("CGPA 8.7") < t.index("Senior Data Engineer")


def test_sections_are_separated():
    """Skills must not bleed into experience — this is what stops a ranker
    treating a keyword-stuffed skills list as evidence of experience."""
    r = extract(FIX / "two_column.pdf")
    assert "skills" in r.sections and "experience" in r.sections
    assert "Kubernetes" in r.sections["skills"]
    assert "Kubernetes" not in r.sections["experience"]
    assert "Acme Corp" in r.sections["experience"]


def test_single_column_does_not_regress():
    r = extract(FIX / "single_column.pdf")
    assert r.pages[0].n_columns == 1
    assert "Senior Data Engineer, Acme Corp" in r.text


# --------------------------------------------------------------------------
# 2. the junk text layer — what `len(text) < 50` cannot catch


def test_junk_text_layer_defeats_the_old_heuristic():
    native = extract(FIX / "junk_layer.pdf", Config(force="native"))
    assert len(native.text.strip()) > 50, "fixture must clear the old threshold"
    assert native.quality.verdict in (Verdict.BAD, Verdict.EMPTY)


def test_junk_text_layer_triggers_ocr_and_recovers_content():
    r = extract(FIX / "junk_layer.pdf")
    assert r.method in (Method.OCR, Method.NATIVE_OCR_PICKED)
    assert "Kubernetes" in r.text and "Acme Corp" in r.text
    assert "ScanPro" not in r.sections.get("skills", "")


def test_scanned_pdf_uses_ocr_with_confidence():
    r = extract(FIX / "scanned.pdf")
    assert r.method == Method.OCR
    assert r.pages[0].ocr_confidence and r.pages[0].ocr_confidence > 80
    assert 0.0 < r.confidence <= 1.0


def test_ocr_path_also_recovers_columns():
    """Column handling must not be native-only — a scan of a two-column resume
    is the common case, and tesseract's own line grouping fuses columns too."""
    r = extract(FIX / "scanned.pdf")
    assert r.pages[0].n_columns == 2
    assert "SKILLS EXPERIENCE" not in r.text
    assert r.text.index("Terraform") < r.text.index("Senior Data Engineer")


def test_clean_pdf_never_pays_for_ocr():
    """Cost control: OCR must not run on a healthy text layer."""
    r = extract(FIX / "single_column.pdf")
    assert r.method == Method.NATIVE
    assert "ocr" not in r.timings_ms


# --------------------------------------------------------------------------
# 3. tables


def test_tables_extracted_and_not_double_counted():
    r = extract(FIX / "table_skills.pdf")
    assert r.tables, "ruled table not detected"
    flat = " ".join(" ".join(row) for t in r.tables for row in t.rows)
    assert "PyTorch" in flat
    assert r.text.count("scikit-learn") == 1, "table text duplicated into the stream"


# --------------------------------------------------------------------------
# 4. DOCX


def test_docx_recovers_textbox_table_header_and_links():
    r = extract(FIX / "designer.docx")
    assert r.doc_format == DocFormat.DOCX
    assert "Python, Django" in r.text, "text box content lost"
    assert r.text.count("CORE SKILLS") == 1, "mc:Fallback duplicate not removed"
    assert "IIT Bombay" in r.text, "table content lost"
    assert any("github.com/rohandesai" in l for l in r.links), "hyperlink target lost"
    assert "rohan.desai@example.com" in r.text, "header content lost"


# --------------------------------------------------------------------------
# 5. robustness


def test_format_sniffing_beats_a_wrong_extension(tmp_path):
    """Applicants rename files. A PDF called .docx must still work."""
    fake = tmp_path / "resume.docx"
    shutil.copy(FIX / "two_column.pdf", fake)
    assert sniff_format(str(fake)) == DocFormat.PDF
    r = extract(fake)
    assert r.ok and "Acme Corp" in r.text
    assert any("trusting content" in w for w in r.warnings)


def test_corrupt_file_returns_error_not_exception(tmp_path):
    """A bad file at position 37 of 500 must not take down the batch."""
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not actually a pdf")
    r = extract(bad)
    assert not r.ok and r.error


def test_duplicate_detection():
    results = extract_batch([FIX / "two_column.pdf", FIX / "two_column_copy.pdf"])
    dups = find_duplicates(results)
    assert dups and dups[0][2] <= 1


def test_batch_is_parallel_and_total_order_stable():
    paths = [FIX / "two_column.pdf", FIX / "single_column.pdf", FIX / "designer.docx"]
    results = extract_batch(paths, Config(workers=3))
    assert [Path(r.path).name for r in results] == [p.name for p in paths]
    assert all(r.ok for r in results)


def test_cli_help_works_without_any_document():
    out = subprocess.run([sys.executable, "-m", "resume_extract.cli", "--help"],
                         capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parents[1]))
    assert out.returncode == 0 and "resume-extract" in out.stdout
