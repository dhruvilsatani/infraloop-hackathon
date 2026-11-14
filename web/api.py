import base64
import json
import os
import re
import secrets
import shutil
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ingest import resolve_repo_path
import uploads
from graph import build_scan_graph, build_report_graph
from nodes.questionnaire import build_questionnaire
from nodes.redact import clean_free_text, clean_answers

app = FastAPI(title="InfraLoop")

# ---------------------------------------------------------------- access code and limits (for a shared review link)
ACCESS_CODE = os.environ.get("INFRALOOP_ACCESS_CODE", "")          # empty = no password (local use)
LIMITS = {                                                          # path prefix -> (max calls, per seconds), per visitor
    "/scan": (int(os.environ.get("INFRALOOP_SCANS_PER_HOUR", "6")), 3600),
    "/answer": (int(os.environ.get("INFRALOOP_REPORTS_PER_HOUR", "6")), 3600),
    "/upload/start": (int(os.environ.get("INFRALOOP_UPLOADS_PER_HOUR", "6")), 3600),
    "/generate": (int(os.environ.get("INFRALOOP_GENERATE_PER_HOUR", "20")), 3600),
    "/targets": (int(os.environ.get("INFRALOOP_TARGETS_PER_HOUR", "60")), 3600),
    "/preview": (int(os.environ.get("INFRALOOP_PREVIEW_PER_HOUR", "120")), 3600),
}
DAILY_REPORTS = int(os.environ.get("INFRALOOP_DAILY_REPORTS", "60"))   # all visitors together
_HITS = defaultdict(deque)
_DAY = {"day": "", "reports": 0}


def _client_ip(request):
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or (request.client.host if request.client else "?"))


def _allowed_by_limits(request):
    if os.environ.get("INFRALOOP_PUBLIC") != "1":      # limits are for the shared link only, never for local use
        return True, ""
    path = request.url.path
    for prefix, (maxn, window) in LIMITS.items():
        if path == prefix and request.method == "POST":
            q, now = _HITS[(prefix, _client_ip(request))], time.time()
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= maxn:
                return False, "Too many requests from your connection. Please try again in a while."
            q.append(now)
    if path == "/answer" and request.method == "POST":
        today = time.strftime("%Y-%m-%d")
        if _DAY["day"] != today:
            _DAY.update(day=today, reports=0)
        if _DAY["reports"] >= DAILY_REPORTS:
            return False, "The daily report limit has been reached. Please try again tomorrow."
        _DAY["reports"] += 1
    return True, ""


@app.middleware("http")
async def guard(request: Request, call_next):
    if ACCESS_CODE:
        sent = ""
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("basic "):
            try:
                sent = base64.b64decode(auth[6:]).decode("utf-8", "ignore").partition(":")[2]
            except Exception:
                sent = ""
        if not secrets.compare_digest(sent.encode(), ACCESS_CODE.encode()):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="InfraLoop review (enter the access code as password)"'})
    ok, msg = _allowed_by_limits(request)
    if not ok:
        return JSONResponse({"detail": msg}, status_code=429)
    return await call_next(request)


STATIC_DIR = Path(__file__).parent / "static"

scan_graph = build_scan_graph()
report_graph = build_report_graph()

# in-memory only -- fine for a local, single-user dev tool. Replace with
# real storage (db.py) once this needs to survive a restart or serve more
# than one person at a time.
SESSIONS = {}

# Sessions are also written to disk, so a server restart / auto-reload (which happens whenever a
# project file changes) does not lose a scan between "scan" and "answer".
SESSION_DIR = Path(__file__).resolve().parent.parent / ".sessions"


def _save_session(session_id, session):
    try:
        SESSION_DIR.mkdir(exist_ok=True)
        (SESSION_DIR / f"{session_id}.json").write_text(json.dumps(session, default=list))
    except Exception:
        pass  # disk persistence is best-effort; the in-memory copy still works


def _load_session(session_id):
    if session_id in SESSIONS:
        return SESSIONS[session_id]
    try:
        uuid.UUID(str(session_id))      # only real session ids; no path tricks
        data = json.loads((SESSION_DIR / f"{session_id}.json").read_text())
        SESSIONS[session_id] = data
        return data
    except Exception:
        return None


NOTES_KEY = "Extra context from you about the project (for example data model or constraints)"


class ScanRequest(BaseModel):
    repo_path_or_url: str = Field(default="", max_length=500)
    upload_id: str = Field(default="", max_length=64)
    notes: str = Field(default="", max_length=20000)


class AnswerRequest(BaseModel):
    session_id: str = Field(max_length=64)
    answers: dict = Field(default_factory=dict)
    mode: str = Field(default="", max_length=10)         # "offline" = report written by rules, no AI model


class UploadBatch(BaseModel):
    files: list = Field(default_factory=list, max_length=uploads.MAX_BATCH_FILES)


@app.post("/upload/start")
def upload_start():
    return {"upload_id": uploads.start_upload()}


@app.post("/upload/{upload_id}/files")
def upload_files(upload_id: str, batch: UploadBatch):
    try:
        return uploads.add_files(upload_id, batch.files)
    except uploads.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/scan")
def start_scan(req: ScanRequest):
    path, is_temp = None, False
    try:
        if req.upload_id:
            path, is_temp = uploads.project_path(req.upload_id), False
        elif req.repo_path_or_url.strip():
            path, is_temp = resolve_repo_path(req.repo_path_or_url)
        else:
            raise RuntimeError("Give a repository link or path, or upload a project folder.")
        state = scan_graph.invoke({"repo_path": path})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if is_temp:
            shutil.rmtree(path, ignore_errors=True)
        if req.upload_id:
            uploads.remove_upload(req.upload_id)      # the scan result is all that is kept; the uploaded code is deleted

    scan_result = state["scan_result"]
    questions = build_questionnaire(scan_result)

    session_id = str(uuid.uuid4())
    asked = [q if isinstance(q, dict) else {"question": q} for q in questions]
    SESSIONS[session_id] = {"asked": asked, "scan_result": scan_result, "gaps": state["gaps"], "notes": clean_free_text(req.notes, 4000)}
    _save_session(session_id, SESSIONS[session_id])

    return {
        "session_id": session_id,
        "questions": questions,
    }

@app.post("/answer")
def submit_answers(req: AnswerRequest):
    session = _load_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="This scan session was lost (the server restarted). Please go back and scan the repo again.")

    if len(req.answers) > 60:
        raise HTTPException(status_code=422, detail="Too many answers.")
    asked = session.get("asked", [])
    known = {q["question"] for q in asked}
    options = {q["question"]: q["options"] for q in asked if q.get("kind") == "choice" and q.get("options")}
    clean = clean_answers(req.answers, known, options)
    if session.get("notes"):
        clean[NOTES_KEY] = session["notes"]
    session["answers"] = {**session.get("answers", {}), **clean}
    _save_session(req.session_id, session)

    from nodes import architecture_reasoner
    architecture_reasoner.set_mode("offline" if req.mode == "offline" else "")
    try:
        state = report_graph.invoke({
            "scan_result": session["scan_result"],
            "gaps": session["gaps"],
            "questionnaire_answers": session["answers"],
            "followup_rounds": session.get("followup_rounds", 0),
        })
    finally:
        architecture_reasoner.set_mode("")

    if state.get("report"):
        ai_error = None if (req.mode == "offline") else architecture_reasoner.LAST_AI_POLISH_ERROR
        return {"status": "done", "report": state["report"], "ai_polish_error": ai_error,
                "ai_written": req.mode != "offline" and not ai_error,
                "gaps": report_gaps(state["report"]), "budget": _budget_for(session)}

    session["followup_rounds"] = session.get("followup_rounds", 0) + 1
    followups = state.get("followup_questions_needed", [])
    session.setdefault("asked", []).extend({"question": q} for q in followups if isinstance(q, str))
    _save_session(req.session_id, session)
    return {"status": "need_more_info", "questions": followups}


def report_gaps(report):
    """The gap table of the finished report as a list, so a page can show the same rows the report has (never a second, different list).
    Each item: name, severity (Critical/High/Medium/Low), group, source, evidence (list of lines)."""
    from nodes import report_cleanup as rc
    try:
        lines = report.split("\n")
        loc = rc._find_gap_table(lines)
        if not loc:
            return []
        a, b = loc
        low = [h.lower() for h in rc._cells(lines[a])]
        def col(*starts):
            return next((k for k, h in enumerate(low) if h.startswith(starts)), None)
        gap_i, sev_i, grp_i, src_i, risk_i = col("gap", "issue", "finding"), col("severity"), col("group"), col("source"), col("risk")
        if gap_i is None or sev_i is None:
            return []
        out = []
        for ln in lines[a + 1:b]:
            cells = rc._cells(ln)
            if len(cells) <= max(gap_i, sev_i) or all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            sev = cells[sev_i].strip().strip("*").capitalize()
            if sev not in ("Critical", "High", "Medium", "Low"):
                continue
            pick = lambda i: cells[i].strip().strip("*") if i is not None and i < len(cells) else ""
            out.append({"name": pick(gap_i), "severity": sev, "group": pick(grp_i), "source": pick(src_i),
                        "evidence": [pick(risk_i)] if pick(risk_i) else []})
        return out
    except Exception as exc:          # the list must never break the report
        print(f"[gaps] not listed: {exc}")
        return []


def _budget_for(session):
    """The monthly budget the user gave (EUR) and whether the recommended setup fits it; monthly_eur is None when no usable budget was given."""
    from nodes import architecture_reasoner as ar
    try:
        scan, answers = session["scan_result"], session.get("answers", {})
        _, cost_data = ar._cost_for(scan, answers)
        plan = ar._plan_for(scan, answers, cost_data) if cost_data else None
        if plan and plan.get("budget") is not None:
            return {"monthly_eur": plan["budget"], "status": plan.get("status")}
    except Exception as exc:
        print(f"[budget] not available: {exc}")
    return {"monthly_eur": None, "status": None}


class GenerateRequest(BaseModel):
    session_id: str = Field(max_length=64)
    target: Optional[str] = Field(default=None, max_length=40)


class TargetsRequest(BaseModel):
    session_id: str = Field(max_length=64)


def _targets_for(session):
    """The 'where will it run?' options for a finished scan, built from the same plan the report used."""
    import generators
    from nodes import architecture_reasoner as ar
    scan, answers = session["scan_result"], session.get("answers", {})
    plan = None
    try:
        _, cost_data = ar._cost_for(scan, answers)
        plan = ar._plan_for(scan, answers, cost_data) if cost_data else None
    except Exception as exc:          # the choice list must never break the page
        print(f"[targets] no plan: {exc}")
    return generators.build_targets(scan, plan, session.get("gaps"))


@app.post("/targets")
def targets(req: TargetsRequest):
    session = _load_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="This scan session was lost (the server restarted). Please scan the repo again.")
    return {"targets": _targets_for(session)}


def _bundle_for(req):
    session = _load_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="This scan session was lost (the server restarted). Please scan the repo again.")
    import generators
    chosen = None
    if req.target:
        chosen = generators.find_target(_targets_for(session), req.target)
        if not chosen:
            raise HTTPException(status_code=422, detail="Unknown choice. Reload the page and pick one of the listed options.")
    return generators.generate_files(session["scan_result"], session["gaps"], chosen)


@app.post("/generate")
def generate(req: GenerateRequest):
    """Starter files (and, for a supported choice, infrastructure files) for an earlier scan. Built from the saved scan facts only:
    the uploaded code is already deleted, no AI model is involved, and nothing is stored."""
    import generators
    bundle = _bundle_for(req)
    return Response(content=generators.to_zip_bytes(bundle), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="infraloop-generated.zip"',
                             "X-Files-Generated": str(len(bundle.files)), "X-Fixes-Advised": str(len(bundle.advice))})


@app.post("/preview")
def preview(req: GenerateRequest):
    """The same files as /generate, as JSON, so the page can show what is in the zip before anyone downloads it."""
    import generators
    from generators.targets import is_cloud_file
    bundle = _bundle_for(req)
    docs = [{"path": "MANIFEST.md", "title": "What each file assumes and what to check", "content": generators.manifest(bundle)}]
    if bundle.implementation:
        docs.insert(0, {"path": "IMPLEMENTATION.md", "title": "What to do with these files, step by step", "content": bundle.implementation})
    if bundle.brief:
        docs.insert(0, {"path": "SETUP.md", "title": "Your chosen setup in plain words", "content": bundle.brief})
    return {"docs": docs,
            "files": [{"path": f.path, "title": f.title, "content": f.content, "group": "cloud" if is_cloud_file(f.path) else "basic"} for f in bundle.files],
            "advice": [{"gap": a.gap, "title": a.title} for a in bundle.advice],
            "skipped": [{"gap": k.gap, "reason": k.reason} for k in bundle.skipped]}


# ---------------------------------------------------------------- pages
# The Angular app (frontend/) is served from here when a production build of it exists: the production image builds it into
# web/frontend_dist. Without a build (local development) "/" is the classic built-in page and the Angular dev server runs on its own port.
FRONTEND_DIR = Path(os.environ.get("INFRALOOP_FRONTEND_DIR") or (Path(__file__).parent / "frontend_dist"))


def _has_frontend():
    return (FRONTEND_DIR / "index.html").is_file()


def _file_under(base, rel):
    """The file `rel` inside `base`, or None. Never a path outside `base`."""
    try:
        target = (base / rel).resolve()
        target.relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    return target if target.is_file() else None


@app.get("/classic", response_class=HTMLResponse)
def classic():
    return (STATIC_DIR / "index.html").read_text()


@app.get("/", response_class=HTMLResponse)
def index():
    if _has_frontend():
        return (FRONTEND_DIR / "index.html").read_text()
    return (STATIC_DIR / "index.html").read_text()


@app.get("/{path:path}")
def page_or_file(path: str):
    """Static files of the Angular build and of the classic page; any other address is a page of the Angular app (it does its own routing)."""
    from fastapi.responses import FileResponse
    found = (_file_under(FRONTEND_DIR, path) if _has_frontend() else None) or _file_under(STATIC_DIR, path)
    if found and found.name != "index.html":
        return FileResponse(found)
    if _has_frontend() and not path.startswith("assets/") and "." not in path.rsplit("/", 1)[-1]:
        return HTMLResponse((FRONTEND_DIR / "index.html").read_text())
    raise HTTPException(status_code=404, detail="Not found")
