"""Temporal coupling: files that historically change together.

Static call graphs miss hidden dependencies — a config and the module that
reads it, a serializer and its schema, duplicated logic kept in sync by
hand. Git history sees them: if two files co-change in most commits that
touch either, changing one without the other is a risk.

    pairs = compute_coupling(repo)
    partners = coupling_map(pairs)["app/tax.py"]   # -> [{"file", "together", "strength"}]

Strength is symmetric confidence: together / min(changes_a, changes_b).
Commits touching more than `max_files_per_commit` files are skipped as
noise (mass reformats, vendored updates, merges).
"""

from __future__ import annotations

import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path

_SEP = "__BLASTRADIUS_COMMIT__"


def compute_coupling(repo: str | Path, max_commits: int = 300,
                     min_together: int = 3, min_strength: float = 0.4,
                     max_files_per_commit: int = 25) -> list[dict]:
    """Return coupled file pairs: [{"a", "b", "together", "strength"}, ...]."""
    out = subprocess.run(
        ["git", "-C", str(repo), "log", f"-n{max_commits}",
         "--name-only", f"--pretty=format:{_SEP}", "--", "*.py"],
        capture_output=True, text=True, check=True,
    ).stdout

    commits: list[list[str]] = []
    current: list[str] = []
    for line in out.splitlines():
        if line == _SEP:
            if current:
                commits.append(current)
            current = []
        elif line.strip().endswith(".py"):
            current.append(line.strip())
    if current:
        commits.append(current)

    file_count: Counter = Counter()
    pair_count: Counter = Counter()
    for files in commits:
        files = sorted(set(files))
        if not files or len(files) > max_files_per_commit:
            continue
        file_count.update(files)
        pair_count.update(combinations(files, 2))

    pairs = []
    for (a, b), together in pair_count.items():
        if together < min_together:
            continue
        strength = round(together / min(file_count[a], file_count[b]), 2)
        if strength >= min_strength:
            pairs.append({"a": a, "b": b, "together": together, "strength": strength})
    pairs.sort(key=lambda p: (-p["strength"], -p["together"]))
    return pairs


def coupling_map(pairs: list[dict]) -> dict[str, list[dict]]:
    """Symmetric lookup: file -> partners sorted by strength."""
    m: dict[str, list[dict]] = {}
    for p in pairs:
        m.setdefault(p["a"], []).append({"file": p["b"], "together": p["together"], "strength": p["strength"]})
        m.setdefault(p["b"], []).append({"file": p["a"], "together": p["together"], "strength": p["strength"]})
    for v in m.values():
        v.sort(key=lambda x: -x["strength"])
    return m
