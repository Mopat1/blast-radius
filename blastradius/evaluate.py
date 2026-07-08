"""Call-resolution evaluation against a ground-truth benchmark suite.

Each benchmark case is a directory containing a tiny Python project plus
an `expected.json` listing every true CALLS edge:

    {"edges": [["main.caller", "main.helper"]], "notes": "..."}

We parse the case, take the predicted CALLS edges, and score:

    precision = TP / (TP + FP)     "when we draw an edge, is it real?"
    recall    = TP / (TP + FN)     "how many real edges do we find?"

Dynamic patterns (higher-order calls, getattr dispatch) are included with
their true edges annotated, so the suite honestly measures what static
analysis cannot see — not just what it can.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .parser.python_parser import PythonParser
from .ir import EdgeKind


@dataclass
class CaseResult:
    name: str
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    spurious: list = field(default_factory=list)   # predicted but not true (FP)
    missing: list = field(default_factory=list)    # true but not predicted (FN)
    notes: str = ""


@dataclass
class EvalResult:
    cases: list[CaseResult] = field(default_factory=list)
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0

    def to_dict(self) -> dict:
        return {"overall": {"tp": self.tp, "fp": self.fp, "fn": self.fn,
                            "precision": self.precision, "recall": self.recall,
                            "f1": self.f1},
                "cases": [asdict(c) for c in self.cases]}


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def evaluate_case(case_dir: str | Path) -> CaseResult:
    case_dir = Path(case_dir)
    spec = json.loads((case_dir / "expected.json").read_text())
    expected = {tuple(e) for e in spec["edges"]}

    doc = PythonParser(case_dir).parse()
    predicted = {(e.src, e.dst) for e in doc.edges if e.kind == EdgeKind.CALLS}

    tp = len(predicted & expected)
    fp_set = predicted - expected
    fn_set = expected - predicted
    p, r, f = _prf(tp, len(fp_set), len(fn_set))
    return CaseResult(
        name=case_dir.name, tp=tp, fp=len(fp_set), fn=len(fn_set),
        precision=p, recall=r, f1=f,
        spurious=sorted(map(list, fp_set)), missing=sorted(map(list, fn_set)),
        notes=spec.get("notes", ""),
    )


def evaluate_all(bench_root: str | Path) -> EvalResult:
    bench_root = Path(bench_root)
    result = EvalResult()
    for case_dir in sorted(p for p in bench_root.iterdir()
                           if p.is_dir() and (p / "expected.json").exists()):
        c = evaluate_case(case_dir)
        result.cases.append(c)
        result.tp += c.tp
        result.fp += c.fp
        result.fn += c.fn
    result.precision, result.recall, result.f1 = _prf(result.tp, result.fp, result.fn)
    return result


def to_markdown(res: EvalResult) -> str:
    lines = [
        "| Case | P | R | F1 | Notes |",
        "|---|---|---|---|---|",
    ]
    for c in res.cases:
        lines.append(f"| {c.name} | {c.precision:.2f} | {c.recall:.2f} | {c.f1:.2f} | {c.notes} |")
    lines.append(f"| **overall (micro)** | **{res.precision:.2f}** | **{res.recall:.2f}** "
                 f"| **{res.f1:.2f}** | {res.tp} TP · {res.fp} FP · {res.fn} FN |")
    return "\n".join(lines)
