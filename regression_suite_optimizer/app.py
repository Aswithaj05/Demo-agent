"""Regression Test Suite Optimizer — web application.

Run:  python app.py        (opens the dashboard in your default browser)

Modes:
- AI mode: set ANTHROPIC_API_KEY — Claude performs the requirement analysis.
- Demo mode: no key needed — a built-in rule-based engine generates the suite.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import engine
import exports

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
PROJECTS_FILE = DATA_DIR / "projects.json"

MAX_FILE_BYTES = 100 * 1024 * 1024

app = FastAPI(title="Regression Test Suite Optimizer")

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load() -> dict:
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {"projects": {}}


def _save(db: dict) -> None:
    PROJECTS_FILE.write_text(json.dumps(db, indent=1), encoding="utf-8")


def _get_project(db: dict, project_id: str) -> dict:
    project = db["projects"].get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _summary(project: dict) -> dict:
    return {
        "id": project["id"],
        "name": project["name"],
        "created": project["created"],
        "files": [f["name"] for f in project["files"]],
        "requirements": len(project["requirements"]),
        "test_cases": len(project["test_cases"]),
        "engine": project.get("engine", ""),
        "analyzed": bool(project["test_cases"]),
        "coverage_percent": (project.get("report") or {}).get("coverage_percent", 0),
        "risk": project.get("risk") or {"score": 0, "level": "n/a"},
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class NewProject(BaseModel):
    name: str


class UploadFilePayload(BaseModel):
    name: str
    content_base64: str
    doc_type: str = "Requirement Document"


class UploadPayload(BaseModel):
    files: list[UploadFilePayload]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/status")
def status() -> dict:
    return {
        "mode": "ai" if engine.ai_available() else "demo",
        "model": "claude-opus-5" if engine.ai_available() else "rule-based engine",
    }


@app.get("/api/projects")
def list_projects() -> list[dict]:
    db = _load()
    projects = sorted(db["projects"].values(), key=lambda p: p["created"], reverse=True)
    return [_summary(p) for p in projects]


@app.post("/api/projects")
def create_project(payload: NewProject) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    with _lock:
        db = _load()
        project = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": [],
            "requirements": [],
            "test_cases": [],
            "report": {},
            "engine": "",
            "duplicates_skipped": 0,
            "duplicate_examples": [],
            "business_rules": [],
            "risk": {"score": 0, "level": "n/a"},
            "insights": {},
            "impact": None,
            "assumptions": [],
            "history": [],
        }
        db["projects"][project["id"]] = project
        _save(db)
    return _summary(project)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    db = _load()
    project = _get_project(db, project_id)
    reqs_by_source: dict[str, list[dict]] = {}
    for r in project["requirements"]:
        reqs_by_source.setdefault(r["source"], []).append(r)
    rules_by_source: dict[str, int] = {}
    for r in project.get("business_rules", []):
        rules_by_source[r["source"]] = rules_by_source.get(r["source"], 0) + 1
    return {
        **_summary(project),
        "file_details": [
            {"name": f["name"], "doc_type": f["doc_type"], "chars": f["chars"],
             "preview": f["preview"], "pages_estimate": f.get("pages_estimate", 1),
             "uploaded_at": f.get("uploaded_at", ""),
             "requirements_found": len(reqs_by_source.get(f["name"], [])),
             "modules_found": sorted({r["module"] for r in reqs_by_source.get(f["name"], [])}),
             "business_rules_found": rules_by_source.get(f["name"], 0)}
            for f in project["files"]
        ],
        "duplicates_skipped": project.get("duplicates_skipped", 0),
        "duplicate_examples": project.get("duplicate_examples", []),
        "business_rules": project.get("business_rules", []),
        "risk": project.get("risk") or {"score": 0, "level": "n/a"},
        "insights": project.get("insights") or {},
        "impact": project.get("impact"),
        "assumptions": project.get("assumptions", []),
        "history": project.get("history", []),
    }


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    with _lock:
        db = _load()
        _get_project(db, project_id)
        del db["projects"][project_id]
        _save(db)
    return {"deleted": project_id}


@app.post("/api/projects/{project_id}/upload")
def upload(project_id: str, payload: UploadPayload) -> dict:
    if not payload.files:
        raise HTTPException(400, "No files provided")
    results = []
    with _lock:
        db = _load()
        project = _get_project(db, project_id)
        for f in payload.files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in engine.SUPPORTED_EXTENSIONS:
                results.append({"name": f.name, "ok": False,
                                 "error": f"Unsupported type {ext or '(none)'} — allowed: PDF, DOCX, XLSX, TXT"})
                continue
            try:
                data = base64.b64decode(f.content_base64, validate=True)
            except (binascii.Error, ValueError):
                results.append({"name": f.name, "ok": False, "error": "Invalid file payload"})
                continue
            if len(data) > MAX_FILE_BYTES:
                results.append({"name": f.name, "ok": False, "error": "File exceeds 100 MB limit"})
                continue
            try:
                text = engine.extract_text(f.name, data)
            except Exception as exc:  # noqa: BLE001 — surface parse failures per file
                results.append({"name": f.name, "ok": False, "error": str(exc)})
                continue
            project["files"] = [x for x in project["files"] if x["name"] != f.name]
            project["files"].append({
                "name": f.name,
                "doc_type": f.doc_type,
                "text": text,
                "chars": len(text),
                "preview": text[:1200],
                "pages_estimate": max(1, -(-len(text) // 3000)),
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            results.append({"name": f.name, "ok": True, "chars": len(text)})
        _save(db)
    return {"results": results, "project": _summary(project)}


@app.post("/api/projects/{project_id}/analyze")
def analyze(project_id: str) -> dict:
    with _lock:
        db = _load()
        project = _get_project(db, project_id)
        if not project["files"]:
            raise HTTPException(400, "Upload at least one document first")
        doc_texts = {f["name"]: f["text"] for f in project["files"]}
        previous_requirements = project["requirements"] or None

    requirements = engine.extract_requirements(doc_texts)
    if not requirements:
        raise HTTPException(
            422,
            "No requirement statements were detected in the uploaded documents. "
            "Check that the documents contain requirement text (e.g. 'The system shall ...').",
        )

    if engine.ai_available():
        try:
            result = engine.ai_generate(requirements, doc_texts)
        except Exception as exc:  # noqa: BLE001 — fall back rather than fail the run
            result = engine.demo_generate(requirements)
            result["engine"] = f"demo (AI call failed: {type(exc).__name__})"
    else:
        result = engine.demo_generate(requirements)

    report = engine.build_report(requirements, result["test_cases"])
    business_rules = engine.extract_business_rules(requirements)
    risk = engine.compute_risk(report, business_rules)
    insights = engine.build_insights(result["test_cases"], report, business_rules,
                                      result.get("duplicate_examples", []))
    impact = engine.compute_impact(previous_requirements, requirements, result["test_cases"])

    with _lock:
        db = _load()
        project = _get_project(db, project_id)
        project["requirements"] = requirements
        project["test_cases"] = result["test_cases"]
        project["report"] = report
        project["engine"] = result["engine"]
        project["duplicates_skipped"] = result["duplicates_skipped"]
        project["duplicate_examples"] = result.get("duplicate_examples", [])
        project["business_rules"] = business_rules
        project["risk"] = risk
        project["insights"] = insights
        project["impact"] = impact
        project["assumptions"] = result.get("assumptions", [])
        project.setdefault("history", []).append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "requirements": len(requirements),
            "test_cases": len(result["test_cases"]),
            "coverage_percent": report["coverage_percent"],
        })
        _save(db)

    return {
        "project": _summary(project),
        "engine": result["engine"],
        "duplicates_skipped": result["duplicates_skipped"],
        "modules": sorted({r["module"] for r in requirements}),
        "report": report,
        "business_rules": business_rules,
        "risk": risk,
        "insights": insights,
        "impact": impact,
        "assumptions": project["assumptions"],
    }


@app.get("/api/projects/{project_id}/testcases")
def testcases(project_id: str) -> dict:
    db = _load()
    project = _get_project(db, project_id)
    return {"test_cases": project["test_cases"], "requirements": project["requirements"]}


@app.get("/api/projects/{project_id}/report")
def report(project_id: str) -> dict:
    db = _load()
    project = _get_project(db, project_id)
    return {
        "report": project["report"],
        "engine": project.get("engine", ""),
        "duplicates_skipped": project.get("duplicates_skipped", 0),
    }


@app.get("/api/projects/{project_id}/insights")
def insights(project_id: str) -> dict:
    db = _load()
    project = _get_project(db, project_id)
    return {
        "insights": project.get("insights") or {},
        "risk": project.get("risk") or {"score": 0, "level": "n/a"},
        "business_rules": project.get("business_rules", []),
    }


@app.get("/api/projects/{project_id}/impact")
def impact(project_id: str) -> dict:
    db = _load()
    project = _get_project(db, project_id)
    return {"impact": project.get("impact"), "history": project.get("history", [])}


class AskPayload(BaseModel):
    question: str


@app.post("/api/projects/{project_id}/ask")
def ask(project_id: str, payload: AskPayload) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, "Question is required")
    db = _load()
    project = _get_project(db, project_id)
    if not project["test_cases"]:
        return {"answer": "Run the analysis first so I have test cases and requirements to talk about."}
    answer = engine.answer_question(question, project)
    return {"answer": answer}


@app.get("/api/projects/{project_id}/export-report/{report_type}")
def export_report(project_id: str, report_type: str) -> Response:
    if report_type not in exports.REPORT_EXPORTERS:
        raise HTTPException(400, f"Unknown report '{report_type}' — use traceability, coverage, impact, or summary")
    db = _load()
    project = _get_project(db, project_id)
    if not project["test_cases"]:
        raise HTTPException(400, "Run the analysis first — there is no report to export")
    func, media_type, ext = exports.REPORT_EXPORTERS[report_type]
    if report_type == "traceability":
        content = func(project["report"])
    elif report_type == "coverage":
        content = func(project["report"], project["name"])
    elif report_type == "impact":
        content = func(project.get("impact"), project["name"])
    else:
        content = func(project["report"], project.get("insights") or {}, project.get("risk") or {},
                        project["name"], project.get("assumptions", []))
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", project["name"]) or "regression_suite"
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_{report_type}.{ext}"'},
    )


@app.get("/api/projects/{project_id}/export/{fmt}")
def export(project_id: str, fmt: str) -> Response:
    if fmt not in exports.EXPORTERS:
        raise HTTPException(400, f"Unknown format '{fmt}' — use csv, xlsx, docx, or pdf")
    db = _load()
    project = _get_project(db, project_id)
    if not project["test_cases"]:
        raise HTTPException(400, "Run the analysis first — there are no test cases to export")
    func, media_type, ext = exports.EXPORTERS[fmt]
    if fmt in ("docx", "pdf"):
        content = func(project["test_cases"], project["name"])
    else:
        content = func(project["test_cases"])
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", project["name"]) or "regression_suite"
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_regression_suite.{ext}"'},
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8756"))
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
