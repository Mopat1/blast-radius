"""BlastRadius Cloud — FastAPI application.

Run:  uvicorn server.main:app --reload
Docs: http://localhost:8000/docs
UI:   http://localhost:8000/
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from blastradius import IRDocument, build_graph, BlastEngine

from .db import init_db, get_db, User, Repo
from .auth import hash_password, verify_password, create_token, current_user
from .analysis import run_analysis

app = FastAPI(title="BlastRadius Cloud", version="0.2.0")
init_db()

STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class RepoIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(description="git URL or local directory path")


# ---------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------

@app.post("/auth/register", status_code=201)
def register(creds: Credentials, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=creds.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=creds.email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
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
    doc = _doc(repo_id, user, db)
    engine = BlastEngine(build_graph(doc))
    matches = engine.find(target)
    if not matches:
        raise HTTPException(404, f"No node matching {target!r}")
    if len(matches) > 1 and target not in matches:
        return {"ambiguous": True, "candidates": matches[:20]}
    return {"ambiguous": False, **engine.blast_radius(matches[0]).to_dict()}


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
