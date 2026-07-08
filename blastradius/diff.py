"""Diff-aware impact analysis.

    git diff -> changed line ranges -> changed functions -> combined blast radius

This is the bridge between "graph explorer" and "impact analysis tool":
instead of asking the user which function changed, we read it from git.

Typical uses:
    diff_impact(repo)                          # uncommitted changes vs HEAD
    diff_impact(repo, base="origin/main")      # a PR branch vs its target
    diff_impact(repo, base="HEAD~3", head="HEAD")
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .parser.python_parser import PythonParser
from .engine import build_graph, BlastEngine, ImpactReport, WEIGHTS, _level

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


# ----------------------------------------------------------------------
# git diff -> {file: [(start, end), ...]}   (new-side line ranges)
# ----------------------------------------------------------------------

def changed_ranges(repo: str | Path, base: str = "HEAD",
                   head: str | None = None) -> dict[str, list[tuple[int, int]]]:
    """Changed line ranges per .py file, on the new side of the diff.

    head=None compares `base` against the working tree (uncommitted work);
    pure deletions are recorded as a 1-line touch point at the deletion site.
    """
    cmd = ["git", "-C", str(repo), "diff", "--unified=0", "--no-color", base]
    if head:
        cmd.append(head)
    cmd += ["--", "*.py"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

    ranges: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = None if path == "/dev/null" else path.removeprefix("b/")
        elif current and (m := _HUNK.match(line)):
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:                      # pure deletion: touch point
                start, end = max(1, start), max(1, start)
            else:
                end = start + count - 1
            ranges.setdefault(current, []).append((start, end))
    return ranges


# ----------------------------------------------------------------------
# ranges -> changed function/method/test nodes
# ----------------------------------------------------------------------

_SYMBOL_KINDS = {"function", "method", "test"}


def functions_for_ranges(graph, ranges: dict[str, list[tuple[int, int]]]
                         ) -> tuple[list[str], list[str]]:
    """Map changed line ranges to graph nodes whose span intersects them.

    Returns (changed_node_ids, unmapped_files). A file is unmapped when it
    changed but no function span covers the change (e.g. module-level code).
    """
    by_file: dict[str, list[tuple[int, int, str]]] = {}
    for n, data in graph.nodes(data=True):
        if data.get("kind") in _SYMBOL_KINDS:
            by_file.setdefault(data.get("file", ""), []).append(
                (data.get("line", 0), data.get("end_line", 0) or data.get("line", 0), n))

    changed: list[str] = []
    unmapped: list[str] = []
    for file, spans in ranges.items():
        symbols = by_file.get(file, [])
        hit = False
        for (s, e) in spans:
            for (fs, fe, nid) in symbols:
                if fs <= e and s <= fe and nid not in changed:   # intervals intersect
                    changed.append(nid)
                    hit = True
        if not hit:
            unmapped.append(file)
    return changed, unmapped


# ----------------------------------------------------------------------
# combined impact
# ----------------------------------------------------------------------

@dataclass
class DiffImpact:
    base: str
    head: str
    changed_functions: list[str] = field(default_factory=list)
    unmapped_files: list[str] = field(default_factory=list)
    reports: dict[str, ImpactReport] = field(default_factory=dict)
    combined: ImpactReport | None = None

    def to_dict(self) -> dict:
        return {
            "base": self.base, "head": self.head,
            "changed_functions": self.changed_functions,
            "unmapped_files": self.unmapped_files,
            "reports": {k: r.to_dict() for k, r in self.reports.items()},
            "combined": self.combined.to_dict() if self.combined else None,
        }


def diff_impact(repo: str | Path, base: str = "HEAD",
                head: str | None = None, use_coupling: bool = False) -> DiffImpact:
    repo = Path(repo).resolve()
    ranges = changed_ranges(repo, base, head)
    result = DiffImpact(base=base, head=head or "WORKTREE")
    if not ranges:
        return result

    graph = build_graph(PythonParser(repo).parse())
    engine = BlastEngine(graph)
    cmap = None
    if use_coupling:
        from .coupling import compute_coupling, coupling_map
        try:
            cmap = coupling_map(compute_coupling(repo))
        except Exception:
            cmap = None
    result.changed_functions, result.unmapped_files = functions_for_ranges(graph, ranges)

    fns, files, eps, tests, coupled = set(), set(), set(), set(), set()
    depth = 0
    for fid in result.changed_functions:
        r = engine.blast_radius(fid, coupling=cmap)
        coupled.update(r.coupled_files)
        result.reports[fid] = r
        fns.update(r.affected_functions)
        files.update(r.affected_files)
        eps.update(r.affected_endpoints)
        tests.update(r.affected_tests)
        depth = max(depth, r.call_depth)
    fns -= set(result.changed_functions)        # changed nodes aren't their own impact

    coupled -= files
    risk = round(WEIGHTS["callers"] * len(fns) + WEIGHTS["endpoints"] * len(eps)
                 + WEIGHTS["tests"] * len(tests) + WEIGHTS["depth"] * depth
                 + WEIGHTS["coupled"] * len(coupled), 2)
    result.combined = ImpactReport(
        target="<combined>",
        affected_functions=sorted(fns), affected_files=sorted(files),
        affected_endpoints=sorted(eps), affected_tests=sorted(tests),
        coupled_files=sorted(coupled),
        call_depth=depth, risk_score=risk, risk_level=_level(risk),
    )
    return result


# ----------------------------------------------------------------------
# GitHub PR comment (Markdown)
# ----------------------------------------------------------------------

_BADGE = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


def to_markdown(d: DiffImpact) -> str:
    """A ready-to-post PR comment."""
    if not d.changed_functions:
        return ("### 💥 BlastRadius\n\nNo Python function changes detected "
                f"between `{d.base}` and `{d.head}`.")
    c = d.combined
    lines = [
        "### 💥 BlastRadius — change impact",
        "",
        f"**Risk: {_BADGE[c.risk_level]} {c.risk_score} ({c.risk_level})** · "
        f"{len(d.changed_functions)} function(s) changed · call depth {c.call_depth}",
        "",
        "| Changed function | Risk | Callers | Endpoints | Tests |",
        "|---|---|---|---|---|",
    ]
    for fid, r in sorted(d.reports.items(), key=lambda kv: -kv[1].risk_score):
        lines.append(f"| `{fid}` | {_BADGE[r.risk_level]} {r.risk_score} | "
                     f"{len(r.affected_functions)} | {len(r.affected_endpoints)} | "
                     f"{len(r.affected_tests)} |")
    if c.affected_endpoints:
        lines += ["", "**API endpoints exposed to this change:**"]
        lines += [f"- `{e}`" for e in c.affected_endpoints[:10]]
    if c.affected_tests:
        lines += ["", f"**Run these {len(c.affected_tests)} test(s):**"]
        lines += [f"- `{t}`" for t in c.affected_tests[:20]]
        if len(c.affected_tests) > 20:
            lines.append(f"- …and {len(c.affected_tests) - 20} more")
    if c.coupled_files:
        lines += ["", ("**\u26a0 Hidden dependencies** \u2014 these files historically "
                       "change together with this code but are outside its static blast radius:")]
        lines += ["- `%s`" % f for f in c.coupled_files[:8]]
    if d.unmapped_files:
        lines += ["", "<sub>Changes outside function bodies (not analyzed): "
                  + ", ".join(f"`{f}`" for f in d.unmapped_files) + "</sub>"]
    return "\n".join(lines)
