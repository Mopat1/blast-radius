"""Diff-aware impact analysis, tested against a real temporary git repo."""
import shutil
import subprocess
from pathlib import Path

import pytest

from blastradius import diff_impact, changed_ranges, to_markdown

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
    return r


def _touch_calc_tax(repo):
    tax = repo / "app" / "tax.py"
    tax.write_text(tax.read_text().replace(
        "return amount * rate", "rate = rate or 0.18\n    return amount * rate"))


def test_worktree_diff_maps_to_function(repo):
    _touch_calc_tax(repo)
    ranges = changed_ranges(repo)                       # vs HEAD, uncommitted
    assert "app/tax.py" in ranges
    d = diff_impact(repo)
    assert d.changed_functions == ["app.tax.calc_tax"]
    assert "endpoint:POST /checkout" in d.combined.affected_endpoints
    assert d.combined.risk_level == "HIGH"


def test_committed_range(repo):
    _touch_calc_tax(repo)
    _git(repo, "commit", "-aqm", "change tax")
    d = diff_impact(repo, base="HEAD~1", head="HEAD")
    assert d.changed_functions == ["app.tax.calc_tax"]
    assert any("test_tax" in t for t in d.combined.affected_tests)


def test_no_changes(repo):
    d = diff_impact(repo)
    assert d.changed_functions == [] and d.combined is None
    assert "No Python function changes" in to_markdown(d)


def test_module_level_change_is_unmapped(repo):
    (repo / "app" / "tax.py").write_text(
        "TAX_TABLE = {}\n" + (repo / "app" / "tax.py").read_text())
    d = diff_impact(repo)
    assert "app/tax.py" in d.unmapped_files


def test_markdown_comment(repo):
    _touch_calc_tax(repo)
    md = to_markdown(diff_impact(repo))
    assert "BlastRadius" in md and "calc_tax" in md
    assert "🔴" in md and "POST /checkout" in md
