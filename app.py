"""FastAPI backend for Odysseus.

    uvicorn backend.app:app --reload --port 8000

Endpoints
---------
    POST   /api/jobs              start a screening run (multipart)
    GET    /api/jobs/{id}         status, progress, logs, result
    GET    /api/jobs/{id}/excel   the workbook for that run
    POST   /api/jobs/{id}/cancel  stop an in-flight run
    DELETE /api/jobs/{id}         discard the run and its uploaded files
    GET    /api/health            liveness plus whether a key is configured

Anything not under /api is served from the built frontend, so one process
serves both in production. In development, run Vite separately and let it proxy
/api here — see the README.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from OCR import extract
from Backend.jobs import JobStore, run_job

# Loaded here rather than relying on the shell, so `uvicorn backend.app:app`
# behaves the same way `python main.py` does.
try:
    from main import load_env
    load_env()
except Exception:                                   # noqa: BLE001
    pass

ALLOWED = {".pdf", ".docx", ".doc"}
MAX_FILE_MB = 15
MAX_FILES = 400
DIST = ROOT / "Frontend" / "dist"

app = FastAPI(title="Odysseus", version="1.0",
              description="Resume screening and ranking.")
store = JobStore()

# Vite dev server runs on another port; production is same-origin so this is
# only doing anything during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173",
                   "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "openaiKeyConfigured": bool(os.environ.get("OPENAI_API_KEY")),
        "frontendBuilt": DIST.is_dir(),
    }


@app.post("/api/jobs", status_code=202)
async def create_job(
    background: BackgroundTasks,
    resumes: List[UploadFile] = File(..., description="PDF or DOCX files"),
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
    offline: bool = Form(False),
    model: str = Form("gpt-4o-mini"),
    workers: int = Form(8),
    top_k: int = Form(3),
) -> JSONResponse:
    """Start a screening run and return immediately with a job id.

    The response is 202, not 200: nothing has been screened yet. Poll
    `/api/jobs/{id}` for progress.
    """
    if not resumes:
        raise HTTPException(400, "At least one resume is required.")
    if len(resumes) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} resumes per run.")
    if not jd_text and not jd_file:
        raise HTTPException(400, "Provide jd_text or jd_file.")
    if not os.environ.get("OPENAI_API_KEY") and not offline:
        raise HTTPException(
            503, "OPENAI_API_KEY is not configured on the server. "
                 "Set it in .env, or send offline=true to use the stub model.")

    workdir = Path(tempfile.mkdtemp(prefix="odysseus_"))
    saved: List[Path] = []

    try:
        for upload in resumes:
            name = Path(upload.filename or "resume").name  # strip any path
            if Path(name).suffix.lower() not in ALLOWED:
                continue
            data = await upload.read()
            if len(data) > MAX_FILE_MB * 1024 * 1024:
                raise HTTPException(
                    413, f"{name} exceeds the {MAX_FILE_MB} MB limit.")
            target = workdir / name
            n = 2
            while target.exists():                  # two files, one name
                target = workdir / f"{Path(name).stem}-{n}{Path(name).suffix}"
                n += 1
            target.write_bytes(data)
            saved.append(target)

        if not saved:
            raise HTTPException(
                400, f"No usable files. Accepted extensions: "
                     f"{', '.join(sorted(ALLOWED))}")

        text = (jd_text or "").strip()
        if jd_file is not None:
            jd_path = workdir / ("jd_" + Path(jd_file.filename or "jd.txt").name)
            jd_path.write_bytes(await jd_file.read())
            if jd_path.suffix.lower() in ALLOWED:
                r = extract(jd_path)                # the JD arrived as a PDF
                if not r.ok:
                    raise HTTPException(400, f"Could not read the JD: {r.error}")
                text = r.text
            else:
                text = jd_path.read_text(encoding="utf-8", errors="replace")

        if not text.strip():
            raise HTTPException(400, "The job description is empty.")

    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    job = store.create(total=len(saved), workdir=workdir)
    job.log(f"Received {len(saved)} resume(s)")

    threading.Thread(
        target=run_job, name=f"job-{job.id}",
        args=(job, text, saved),
        kwargs={"offline": offline, "model": model,
                "workers": max(1, min(workers, 16)), "top_k": max(1, top_k)},
        daemon=True,
    ).start()

    return JSONResponse({"jobId": job.id, "total": len(saved),
                         "statusUrl": f"/api/jobs/{job.id}"}, status_code=202)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, logs_from: int = 0) -> dict:
    """Progress and, once finished, the result.

    `logs_from` lets a poller ask only for log lines it has not seen, so the
    payload stays small on a long run.
    """
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job. It may have expired.")
    payload = job.public(include_result=job.status == "done")
    payload["logs"] = job.logs[logs_from:]
    payload["logsTotal"] = len(job.logs)
    return payload


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    job._cancel.set()
    return {"jobId": job.id, "cancelling": True}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    """Discard a run and the uploaded resumes with it."""
    if not store.remove(job_id):
        raise HTTPException(404, "No such job.")
    return {"deleted": job_id}


@app.get("/api/jobs/{job_id}/excel")
def job_excel(job_id: str) -> FileResponse:
    """The run as a spreadsheet — the practical export for a hiring manager."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    if job.status != "done" or not job.result:
        raise HTTPException(409, f"Job is {job.status}; nothing to export yet.")

    try:
        from Excel.export_excel import export
    except Exception as exc:                        # noqa: BLE001
        raise HTTPException(501, f"Excel export unavailable: {exc}")

    import json
    ranking = {
        "job": {"role_title": job.result["jobTitle"]},
        "shortlist": [_as_ranking_row(c) for c in job.result["candidates"]],
        "duplicates_folded": [_as_ranking_row(c)
                              for c in job.result["duplicatesFolded"]],
    }
    tmp = job.workdir / "ranking.json"
    tmp.write_text(json.dumps(ranking), encoding="utf-8")
    out = job.workdir / "rankings.xlsx"
    export([tmp], out)

    safe = "".join(ch for ch in job.result["jobTitle"]
                   if ch.isalnum() or ch in " -_").strip() or "rankings"
    return FileResponse(out, filename=f"{safe}.xlsx",
                        media_type="application/vnd.openxmlformats-"
                                   "officedocument.spreadsheetml.sheet")


def _as_ranking_row(c: dict) -> dict:
    """Frontend candidate -> the ranking.json shape the exporter expects."""
    return {
        "path": c["fileName"], "rank": c.get("rank"), "score": c["matchScore"],
        "summary": c["summary"], "explanation": c.get("explanation", ""),
        "matched_skills": c["skills"], "missing_or_weak": c["gaps"],
        "components": c.get("components", []), "flags": c.get("flags", []),
        "extraction_confidence": c.get("extractionConfidence", 1.0),
        "duplicate_of": c.get("duplicateOf"), "duplicates": [],
        "assessments": [],
        "experience": {"years": None} if c["experienceYears"] == "Not stated"
        else {"years": float(c["experienceYears"].split()[0]),
              "method": "date-ranges", "evidence": []},
    }


# ---------------------------------------------------------------------------
# static frontend — mounted last so /api always wins


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="frontend")
else:
    @app.get("/")
    def no_build() -> dict:
        return {"message": "Frontend not built. Run `npm install && npm run "
                           "build` in Frontend/, or use the Vite dev server on "
                           "port 3000 with /api proxied here.",
                "api": "/docs"}