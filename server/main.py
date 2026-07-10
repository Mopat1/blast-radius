"""BlastRadius Cloud — FastAPI application.

Run:  uvicorn server.main:app --reload
Docs: http://localhost:8000/docs
UI:   http://localhost:8000/
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from blastradius import IRDocument, build_graph, BlastEngine

from .db import init_db, get_db, User, Repo
from .auth import hash_password, verify_password, create_token, current_user
from .analysis import run_analysis

app = FastAPI(title="BlastRadius Cloud", version="0.3.0")

# CORS: needed when the frontend is hosted separately (e.g. Netlify).
# Set BLASTRADIUS_CORS to a comma-separated list of origins in production.
import os as _os
_origins = [o.strip() for o in _os.environ.get("BLASTRADIUS_CORS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=_origins,
                   allow_methods=["*"], allow_headers=["*"])

# GZip: the graph JSON for large repos compresses ~85% over the wire.
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def static_no_cache(request, call_next):
    """Force revalidation of frontend assets so deploys are picked up
    immediately (stale ES-module caches otherwise mix old and new code)."""
    response = await call_next(request)
    p = request.url.path
    if p == "/" or p.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response

init_db()


@app.get("/health", include_in_schema=False)
def health():
    """Deployment health check (configure this path in Render)."""
    return {"status": "ok", "version": "0.7.0"}


DEMO_EMAIL = "demo@blastradius.dev"
DEMO_REPO_SOURCE = _os.environ.get("BLASTRADIUS_DEMO_REPO",
                                  "https://github.com/pallets/click")


@app.post("/auth/demo")
def demo_login(tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Product-led onboarding: instant demo account preloaded with a real repo."""
    import secrets
    user = db.query(User).filter_by(email=DEMO_EMAIL).first()
    if user is None:
        user = User(email=DEMO_EMAIL,
                    password_hash=hash_password(secrets.token_hex(16)))
        db.add(user)
        db.commit()
    repo = db.query(Repo).filter_by(owner_id=user.id, name="click-demo").first()
    if repo is None:
        repo = Repo(owner_id=user.id, name="click-demo", source=DEMO_REPO_SOURCE)
        db.add(repo)
        db.commit()
        tasks.add_task(run_analysis, repo.id)
    return {"token": create_token(user), "email": user.email}

STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class ExplainIn(BaseModel):
    target: str


class LayoutIn(BaseModel):
    layout: dict


class RepoIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(description="git URL or local directory path")


# ---------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------

SAMPLE_REPO = _os.environ.get("BLASTRADIUS_SAMPLE_REPO", "")


def _seed_sample_repo(user: User, db: Session, tasks: BackgroundTasks) -> None:
    """Give every new account an already-queued sample repository so the
    first-run experience is one click, not a form."""
    if not SAMPLE_REPO:
        return
    repo = Repo(owner_id=user.id, name="blastradius (sample)", source=SAMPLE_REPO)
    db.add(repo)
    db.commit()
    tasks.add_task(run_analysis, repo.id)


@app.post("/auth/register", status_code=201)
def register(creds: Credentials, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=creds.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=creds.email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    _seed_sample_repo(user, db, tasks)
    return {"token": create_token(user), "email": user.email}


@app.post("/auth/login")
def login(creds: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=creds.email).first()
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return {"token": create_token(user), "email": user.email}


# ---------------------------------------------------------------------
# repositories
# ---------------------------------------------------------------------

def _repo_out(r: Repo) -> dict:
    return {
        "id": r.id, "name": r.name, "source": r.source, "status": r.status,
        "error": r.error,
        "n_nodes": r.analysis.n_nodes if r.analysis else 0,
        "n_edges": r.analysis.n_edges if r.analysis else 0,
    }


@app.get("/repos")
def list_repos(user: User = Depends(current_user)):
    return [_repo_out(r) for r in user.repos]


@app.post("/repos", status_code=201)
def create_repo(body: RepoIn, tasks: BackgroundTasks,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(Repo).filter_by(owner_id=user.id, name=body.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Repo name already exists")
    repo = Repo(owner_id=user.id, name=body.name, source=body.source)
    db.add(repo)
    db.commit()
    tasks.add_task(run_analysis, repo.id)
    return _repo_out(repo)


@app.post("/repos/{repo_id}/analyze")
def reanalyze(repo_id: int, tasks: BackgroundTasks,
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = _owned(repo_id, user, db)
    repo.status = "pending"
    db.commit()
    tasks.add_task(run_analysis, repo.id)
    return _repo_out(repo)


@app.delete("/repos/{repo_id}", status_code=204)
def delete_repo(repo_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    db.delete(_owned(repo_id, user, db))
    db.commit()


# ---------------------------------------------------------------------
# analysis results
# ---------------------------------------------------------------------

@app.get("/repos/{repo_id}/graph")
def graph(repo_id: int, user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    doc = _doc(repo_id, user, db)
    return doc.to_dict()


@app.get("/repos/{repo_id}/impact")
def impact(repo_id: int, target: str, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    from blastradius import coupling_map
    repo = _owned(repo_id, user, db)
    doc = _doc(repo_id, user, db)
    engine = BlastEngine(build_graph(doc))
    matches = engine.find(target)
    if not matches:
        raise HTTPException(404, f"No node matching {target!r}")
    if len(matches) > 1 and target not in matches:
        return {"ambiguous": True, "candidates": matches[:20]}
    cmap = None
    try:
        pairs = json.loads(repo.analysis.coupling_json or "[]")
        cmap = coupling_map(pairs) if pairs else None
    except Exception:
        cmap = None
    return {"ambiguous": False, **engine.blast_radius(matches[0], coupling=cmap).to_dict()}


@app.get("/repos/{repo_id}/hotspots")
def hotspots(repo_id: int, limit: int = 10, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Top-N riskiest functions in the repo, by blast-radius score."""
    doc = _doc(repo_id, user, db)
    engine = BlastEngine(build_graph(doc))
    scored = []
    for n, data in engine.g.nodes(data=True):
        if data.get("kind") in ("function", "method"):
            r = engine.blast_radius(n)
            scored.append({
                "id": n, "risk": r.risk_score, "level": r.risk_level,
                "callers": len(r.affected_functions),
                "endpoints": len(r.affected_endpoints),
                "tests": len(r.affected_tests),
                "file": data.get("file"), "line": data.get("line"),
            })
    scored.sort(key=lambda x: -x["risk"])
    return {"hotspots": scored[:max(1, min(limit, 50))]}


@app.post("/repos/{repo_id}/explain")
def explain(repo_id: int, body: ExplainIn, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """AI reviewer note for a target's blast radius (needs ANTHROPIC_API_KEY)."""
    from . import ai
    from blastradius import coupling_map
    if not ai.is_configured():
        raise HTTPException(503, "AI explanations are not configured on this server "
                                 "(set GEMINI_API_KEY).")
    repo = _owned(repo_id, user, db)
    doc = _doc(repo_id, user, db)
    engine = BlastEngine(build_graph(doc))
    matches = engine.find(body.target)
    if not matches:
        raise HTTPException(404, f"No node matching {body.target!r}")
    if len(matches) > 1 and body.target not in matches:
        raise HTTPException(400, "Ambiguous target; pass a fully qualified name.")
    cmap = None
    try:
        import json as _json
        pairs = _json.loads(repo.analysis.coupling_json or "[]")
        cmap = coupling_map(pairs) if pairs else None
    except Exception:
        cmap = None
    report = engine.blast_radius(matches[0], coupling=cmap).to_dict()
    try:
        text = ai.explain_impact(report)
    except Exception as exc:
        raise HTTPException(502, f"AI request failed: {exc}")
    return {"target": matches[0], "explanation": text}


@app.get("/repos/{repo_id}/layout")
def get_layout(repo_id: int, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    repo = _owned(repo_id, user, db)
    return {"layout": json.loads(repo.layout_json) if repo.layout_json else None}


@app.put("/repos/{repo_id}/layout")
def put_layout(repo_id: int, body: LayoutIn, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    repo = _owned(repo_id, user, db)
    repo.layout_json = json.dumps(body.layout)
    db.commit()
    return {"ok": True}


@app.get("/repos/{repo_id}/search")
def search(repo_id: int, q: str, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    doc = _doc(repo_id, user, db)
    ql = q.lower()
    hits = [
        {"id": n.id, "kind": n.kind.value, "file": n.file, "line": n.line}
        for n in doc.nodes if ql in n.id.lower()
    ]
    return {"query": q, "results": hits[:50]}


# ---------------------------------------------------------------------
# helpers + static UI
# ---------------------------------------------------------------------

def _owned(repo_id: int, user: User, db: Session) -> Repo:
    repo = db.get(Repo, repo_id)
    if repo is None or repo.owner_id != user.id:
        raise HTTPException(404, "Repo not found")
    return repo


def _doc(repo_id: int, user: User, db: Session) -> IRDocument:
    repo = _owned(repo_id, user, db)
    if repo.status != "ready" or repo.analysis is None:
        raise HTTPException(409, f"Analysis not ready (status: {repo.status})")
    return IRDocument.from_dict(json.loads(repo.analysis.ir_json))


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
