"""BlastRadius — know what breaks before you merge."""
from .ir import IRDocument, IRNode, IREdge, NodeKind, EdgeKind
from .engine import build_graph, BlastEngine, ImpactReport
from .parser.python_parser import PythonParser
from .diff import diff_impact, changed_ranges, DiffImpact, to_markdown
from .coupling import compute_coupling, coupling_map

__version__ = "0.1.0"
__all__ = ["IRDocument", "IRNode", "IREdge", "NodeKind", "EdgeKind",
           "build_graph", "BlastEngine", "ImpactReport", "PythonParser",
           "diff_impact", "changed_ranges", "DiffImpact", "to_markdown",
           "compute_coupling", "coupling_map"]
