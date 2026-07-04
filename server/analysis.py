"""Background analysis job for BlastRadius Cloud.

MVP runs jobs with FastAPI BackgroundTasks in-process.
Swap point: move `run_analysis` into a Celery task with Redis broker
for horizontal scaling — the function body stays identical.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from blastradius import PythonParser

from .db import SessionLocal, Repo, Analysis


def run_analysis(repo_id: int) -> None:
    db = SessionLocal()
    try:
        repo = db.get(Repo, repo_id)
        if repo is None:
            return
        repo.status = "analyzing"
        db.commit()

        workdir = None
        try:
            path = _materialize(repo.source)
            if isinstance(path, tuple):        # (tmpdir, path) for cloned repos
                workdir, path = path

            doc = PythonParser(path).parse()

            db.query(Analysis).filter_by(repo_id=repo.id).delete()
            db.add(Analysis(
                repo_id=repo.id,
                ir_json=doc.to_json(indent=0),
                n_nodes=len(doc.nodes),
                n_edges=len(doc.edges),
            ))
            repo.status = "ready"
            repo.error = ""
        except Exception as exc:  # noqa: BLE001 — surfaced to the user via status
            repo.status = "failed"
            repo.error = str(exc)[:500]
        finally:
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)
        db.commit()
    finally:
        db.close()


def _materialize(source: str):
    """Return a local path for `source` — clone if it's a git URL."""
    if source.startswith(("http://", "https://", "git@")):
        tmpdir = tempfile.mkdtemp(prefix="blastradius-")
        subprocess.run(
            ["git", "clone", "--depth", "1", source, tmpdir],
            check=True, capture_output=True, timeout=300,
        )
        return (tmpdir, tmpdir)
    p = Path(source).expanduser().resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"Not a directory: {source}")
    return str(p)
