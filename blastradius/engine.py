"""Graph builder + Blast Radius engine.

    IR -> NetworkX DiGraph -> impact analysis + risk score
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import networkx as nx

from .ir import IRDocument, NodeKind, EdgeKind


# ----------------------------------------------------------------------
# Graph builder
# ----------------------------------------------------------------------

def build_graph(doc: IRDocument) -> nx.MultiDiGraph:
    """Turn an IRDocument into a directed multigraph.

    Edge direction follows the IR:  caller --CALLS--> callee.
    Impact traversal therefore walks CALLS edges *in reverse*
    (who depends on me), and EXPOSES/TESTS edges forward from
    affected nodes.
    """
    g = nx.MultiDiGraph()
    known = doc.node_ids()
    for n in doc.nodes:
        g.add_node(n.id, kind=n.kind.value, name=n.name,
                   file=n.file, line=n.line, end_line=n.end_line, **n.meta)
    for e in doc.edges:
        # keep only edges whose endpoints exist (drops unresolved externals)
        if e.src in known and e.dst in known:
            g.add_edge(e.src, e.dst, kind=e.kind.value)
    return g


# ----------------------------------------------------------------------
# Blast radius
# ----------------------------------------------------------------------

@dataclass
class ImpactReport:
    target: str
    affected_functions: list[str] = field(default_factory=list)   # upstream callers
    affected_files: list[str] = field(default_factory=list)
    affected_endpoints: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    coupled_files: list = field(default_factory=list)   # hidden deps from git history
    call_depth: int = 0
    risk_score: float = 0.0
    risk_level: str = "LOW"

    def to_dict(self) -> dict:
        return asdict(self)


# Risk = 0.4·callers + 0.3·endpoints + 0.2·tests + 0.1·depth
WEIGHTS = {"callers": 0.4, "endpoints": 0.3, "tests": 0.2, "depth": 0.1, "coupled": 0.15}


class BlastEngine:
    def __init__(self, graph: nx.MultiDiGraph):
        self.g = graph

    # -- queries --------------------------------------------------------

    def find(self, needle: str) -> list[str]:
        """Find node ids matching a (partial) qualified name."""
        if needle in self.g:
            return [needle]
        return sorted(
            n for n in self.g.nodes
            if n.endswith("." + needle) or needle in n
        )

    def blast_radius(self, target: str, coupling: dict | None = None) -> ImpactReport:
        """coupling: optional file->partners map (blastradius.coupling.coupling_map).
        Co-changing files outside the static blast radius are reported as
        hidden dependencies, each adding 0.15 to the risk score."""
        if target not in self.g:
            raise KeyError(f"Node not found in graph: {target!r}")

        # 1. Upstream impact: everything that (transitively) CALLS the target.
        callers, depth = self._upstream(target)

        affected = {target, *callers}

        # 2. Surface: endpoints EXPOSED by any affected function.
        endpoints = set()
        # 3. Tests: anything that TESTS an affected function.
        tests = set()
        for node in affected:
            for _, dst, data in self.g.out_edges(node, data=True):
                if data.get("kind") == EdgeKind.EXPOSES.value:
                    endpoints.add(dst)
            for src, _, data in self.g.in_edges(node, data=True):
                if data.get("kind") == EdgeKind.TESTS.value:
                    tests.add(src)

        files = sorted({
            self.g.nodes[n].get("file", "?")
            for n in affected if self.g.nodes[n].get("kind") != NodeKind.MODULE.value
        })

        coupled = []
        if coupling:
            own_file = self.g.nodes[target].get("file", "")
            seen = set(files)
            coupled = [p["file"] for p in coupling.get(own_file, [])
                       if p["file"] not in seen and p["file"] != own_file]

        n_callers, n_eps, n_tests = len(callers), len(endpoints), len(tests)
        risk = round(
            WEIGHTS["callers"] * n_callers
            + WEIGHTS["endpoints"] * n_eps
            + WEIGHTS["tests"] * n_tests
            + WEIGHTS["depth"] * depth
            + WEIGHTS["coupled"] * len(coupled), 2,
        )

        return ImpactReport(
            target=target,
            coupled_files=coupled,
            affected_functions=sorted(callers),
            affected_files=files,
            affected_endpoints=sorted(endpoints),
            affected_tests=sorted(tests),
            call_depth=depth,
            risk_score=risk,
            risk_level=_level(risk),
        )

    # -- internals -------------------------------------------------------

    def _upstream(self, target: str) -> tuple[set[str], int]:
        """BFS over reversed CALLS edges: who breaks if `target` changes."""
        visited: set[str] = set()
        frontier = {target}
        depth = 0
        while frontier:
            nxt: set[str] = set()
            for node in frontier:
                for src, _, data in self.g.in_edges(node, data=True):
                    if data.get("kind") == EdgeKind.CALLS.value and src not in visited and src != target:
                        visited.add(src)
                        nxt.add(src)
            if nxt:
                depth += 1
            frontier = nxt
        return visited, depth


def _level(risk: float) -> str:
    if risk >= 3.0:
        return "HIGH"
    if risk >= 1.5:
        return "MEDIUM"
    return "LOW"
