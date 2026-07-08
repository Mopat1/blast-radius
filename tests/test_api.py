"""API tests for BlastRadius Cloud using FastAPI's TestClient."""
import os, tempfile, time
os.environ["BLASTRADIUS_DB"] = "sqlite:///" + tempfile.mktemp(suffix=".db")

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from server.main import app
from server.analysis import run_analysis

SHOP = str(Path(__file__).parent.parent / "examples" / "shop")
client = TestClient(app)


@pytest.fixture(scope="module")
def token():
    r = client.post("/auth/register", json={"email": "t@t.com", "password": "secret123"})
    assert r.status_code == 201
    return r.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_duplicate(token):
    r = client.post("/auth/register", json={"email": "t@t.com", "password": "secret123"})
    assert r.status_code == 409


def test_login_wrong_password(token):
    r = client.post("/auth/login", json={"email": "t@t.com", "password": "nope!!"})
    assert r.status_code == 401


def test_repos_require_auth():
    assert client.get("/repos").status_code == 401


def test_repo_lifecycle(token):
    r = client.post("/repos", json={"name": "shop", "source": SHOP}, headers=auth(token))
    assert r.status_code == 201
    repo_id = r.json()["id"]

    # TestClient runs background tasks after response; poll for ready
    for _ in range(20):
        status = client.get("/repos", headers=auth(token)).json()[0]["status"]
        if status == "ready":
            break
        time.sleep(0.2)
    assert status == "ready"

    # impact via API
    r = client.get(f"/repos/{repo_id}/impact", params={"target": "calc_tax"}, headers=auth(token))
    d = r.json()
    assert d["risk_level"] == "HIGH"
    assert "endpoint:POST /checkout" in d["affected_endpoints"]

    # search
    r = client.get(f"/repos/{repo_id}/search", params={"q": "charge"}, headers=auth(token))
    assert any("payments.charge" in h["id"] for h in r.json()["results"])

    # graph
    g = client.get(f"/repos/{repo_id}/graph", headers=auth(token)).json()
    assert g["language"] == "python" and len(g["nodes"]) > 10

    # delete
    assert client.delete(f"/repos/{repo_id}", headers=auth(token)).status_code == 204


def test_failed_analysis_surfaces_error(token):
    r = client.post("/repos", json={"name": "bad", "source": "/does/not/exist"}, headers=auth(token))
    repo_id = r.json()["id"]
    run_analysis(repo_id)
    repos = client.get("/repos", headers=auth(token)).json()
    bad = next(x for x in repos if x["id"] == repo_id)
    assert bad["status"] == "failed" and "Not a directory" in bad["error"]


def test_hotspots(token):
    r = client.post("/repos", json={"name": "shop2", "source": SHOP}, headers=auth(token))
    repo_id = r.json()["id"]
    for _ in range(20):
        if client.get("/repos", headers=auth(token)).json()[-1]["status"] == "ready":
            break
        time.sleep(0.2)
    d = client.get(f"/repos/{repo_id}/hotspots", headers=auth(token)).json()
    hs = d["hotspots"]
    assert hs and hs[0]["risk"] >= hs[-1]["risk"]          # sorted desc
    assert any("calc_tax" in h["id"] for h in hs)          # known hottest symbol present


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_demo_login():
    d = client.post("/auth/demo").json()
    assert d["email"] == "demo@blastradius.dev"
    repos = client.get("/repos", headers=auth(d["token"])).json()
    assert any(r["name"] == "click-demo" for r in repos)
    # idempotent: second call reuses the same account/repo
    d2 = client.post("/auth/demo").json()
    assert client.get("/repos", headers=auth(d2["token"])).json()[0]["name"] == "click-demo"
