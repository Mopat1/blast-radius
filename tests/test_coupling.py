"""Temporal coupling: mined from a synthetic git history."""
import shutil
import subprocess
from pathlib import Path

import pytest

from blastradius import (compute_coupling, coupling_map, PythonParser,
                         build_graph, BlastEngine, diff_impact, to_markdown)

SHOP = Path(__file__).parent.parent / "examples" / "shop"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "shop"
    shutil.copytree(SHOP, r)
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t.com")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "."); _git(r, "commit", "-qm", "init")
    # tax.py and payments.py co-change 4 times; cart.py changes alone twice
    for i in range(4):
        (r/"app"/"tax.py").write_text((r/"app"/"tax.py").read_text() + f"\n# rev {i}\n")
        (r/"app"/"payments.py").write_text((r/"app"/"payments.py").read_text() + f"\n# rev {i}\n")
        _git(r, "commit", "-aqm", f"tax+payments {i}")
    for i in range(2):
        (r/"app"/"cart.py").write_text((r/"app"/"cart.py").read_text() + f"\n# solo {i}\n")
        _git(r, "commit", "-aqm", f"cart {i}")
    return r


def test_pairs_detected(repo):
    pairs = compute_coupling(repo, min_together=3, min_strength=0.4)
    top = pairs[0]
    assert {top["a"], top["b"]} == {"app/payments.py", "app/tax.py"}
    assert top["together"] >= 4 and top["strength"] >= 0.8


def test_engine_reports_hidden_dependency_and_risk_bump(repo):
    cmap = coupling_map(compute_coupling(repo))
    eng = BlastEngine(build_graph(PythonParser(repo).parse()))
    plain = eng.blast_radius("app.tax.calc_tax")
    with_c = eng.blast_radius("app.tax.calc_tax", coupling=cmap)
    # payments.py is already in the static radius, so only files OUTSIDE it count
    assert set(with_c.coupled_files).isdisjoint(set(with_c.affected_files))
    assert with_c.risk_score >= plain.risk_score


def test_hidden_dep_outside_static_radius(repo):
    # refund has a tiny static radius; couple its file to cart.py history-wise
    cmap = coupling_map(compute_coupling(repo))
    eng = BlastEngine(build_graph(PythonParser(repo).parse()))
    r = eng.blast_radius("app.payments.refund", coupling=cmap)
    assert "app/tax.py" in r.coupled_files          # co-changed, not in static radius
    plain = eng.blast_radius("app.payments.refund")
    assert r.risk_score == round(plain.risk_score + 0.15 * len(r.coupled_files), 2)


def test_diff_markdown_includes_hidden_deps(repo):
    p = repo/"app"/"payments.py"
    p.write_text(p.read_text().replace('return {"status": "refunded"', 'order_id = str(order_id)\n    return {"status": "refunded"'))
    d = diff_impact(repo, use_coupling=True)
    assert "app.payments.refund" in d.changed_functions
    md = to_markdown(d)
    assert "Hidden dependencies" in md and "app/tax.py" in md
