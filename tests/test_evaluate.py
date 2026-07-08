"""The evaluation suite itself is under test: known-easy cases must be
perfect, known-dynamic cases must be honest misses, and precision must
stay at 1.0 (the resolver never guesses)."""
from pathlib import Path

from blastradius import evaluate_all

BENCH = Path(__file__).parent.parent / "benchmarks"


def test_overall_scores():
    res = evaluate_all(BENCH)
    assert len(res.cases) >= 12
    assert res.fp == 0                       # never a spurious edge
    assert res.precision == 1.0
    assert 0.75 <= res.recall < 1.0          # dynamic cases are honest misses


def test_static_cases_are_perfect():
    res = evaluate_all(BENCH)
    perfect = {"direct_call", "import_from", "import_module", "import_alias",
               "self_method", "nested_function", "method_unique", "decorator",
               "inheritance_call", "ambiguous_name"}
    by_name = {c.name: c for c in res.cases}
    for name in perfect:
        assert by_name[name].f1 == 1.0, f"{name}: {by_name[name]}"


def test_dynamic_cases_miss_honestly():
    res = evaluate_all(BENCH)
    by_name = {c.name: c for c in res.cases}
    assert by_name["dynamic_getattr"].recall == 0.0
    assert by_name["dynamic_getattr"].fp == 0
    assert by_name["higher_order"].fn == 1   # fn() through a parameter
