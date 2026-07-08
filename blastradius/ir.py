"""Intermediate Representation (IR) for BlastRadius.

Every language parser emits this same format. The graph builder consumes it.
This is the architectural seam that makes the engine language-agnostic:

    Parser -> IR -> Graph Builder -> Graph
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json


class NodeKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    API_ENDPOINT = "api_endpoint"
    TEST = "test"


class EdgeKind(str, Enum):
    CONTAINS = "CONTAINS"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    EXPOSES = "EXPOSES"
    TESTS = "TESTS"


@dataclass
class IRNode:
    """A single entity in the codebase (module, class, function, ...)."""

    id: str                      # fully-qualified name, e.g. "app.payments.charge"
    kind: NodeKind
    name: str                    # short name, e.g. "charge"
    file: str                    # relative file path
    line: int = 0
    end_line: int = 0            # inclusive last line of the definition
    meta: dict = field(default_factory=dict)   # e.g. {"http_method": "POST", "route": "/checkout"}


@dataclass
class IREdge:
    """A relationship between two entities."""

    src: str
    dst: str
    kind: EdgeKind


@dataclass
class IRDocument:
    """The complete IR for one repository — what a parser hands to the graph builder."""

    language: str
    root: str
    nodes: list[IRNode] = field(default_factory=list)
    edges: list[IREdge] = field(default_factory=list)

    # ---- convenience -------------------------------------------------

    def add_node(self, node: IRNode) -> None:
        self.nodes.append(node)

    def add_edge(self, src: str, dst: str, kind: EdgeKind) -> None:
        self.edges.append(IREdge(src=src, dst=dst, kind=kind))

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    # ---- serialization -----------------------------------------------

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "root": self.root,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "IRDocument":
        doc = cls(language=data["language"], root=data["root"])
        for n in data["nodes"]:
            doc.add_node(IRNode(
                id=n["id"], kind=NodeKind(n["kind"]), name=n["name"],
                file=n["file"], line=n.get("line", 0),
                end_line=n.get("end_line", 0), meta=n.get("meta", {}),
            ))
        for e in data["edges"]:
            doc.add_edge(e["src"], e["dst"], EdgeKind(e["kind"]))
        return doc
