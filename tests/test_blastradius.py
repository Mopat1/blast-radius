"""End-to-end tests: parse the example shop repo, build graph, compute impact."""
from pathlib import Path

import pytest

from blastradius import PythonParser, build_graph, BlastEngine, NodeKind

SHOP = Path(__file__).parent.parent / "examples" / "shop"


@pytest.fixture(scope="module")
def engine():
    doc = PythonParser(SHOP).parse()
    return BlastEngine(build_graph(doc)), doc


def test_parser_finds_entities(engine):
    _, doc = engine
    kinds = {n.kind for n in doc.nodes}
    assert NodeKind.FUNCTION in kinds
    assert NodeKind.TEST in kinds
    assert NodeKind.API_ENDPOINT in kinds
    ids = doc.node_ids()
    assert "app.tax.calc_tax" in ids
    assert "app.payments.charge" in ids
    assert "endpoint:POST /checkout" in ids


def test_call_resolution(engine):
    _, doc = engine
    calls = {(e.src, e.dst) for e in doc.edges if e.kind.value == "CALLS"}
    assert ("app.cart.cart_total", "app.tax.calc_tax") in calls
    assert ("app.payments.charge", "app.cart.cart_total") in calls
    assert ("app.api.checkout", "app.payments.charge") in calls


def test_blast_radius_of_calc_tax(engine):
    eng, _ = engine
    r = eng.blast_radius("app.tax.calc_tax")
    # upstream ripple: cart_total -> charge -> checkout (+ test callers)
    assert "app.cart.cart_total" in r.affected_functions
    assert "app.payments.charge" in r.affected_functions
    assert "app.api.checkout" in r.affected_functions
    assert "endpoint:POST /checkout" in r.affected_endpoints
    assert any("test_tax" in t or "test_charge" in t for t in r.affected_tests)
    assert r.call_depth >= 3
    assert r.risk_score > 0


def test_leaf_function_low_risk(engine):
    eng, _ = engine
    r = eng.blast_radius("app.payments.refund")
    tax = eng.blast_radius("app.tax.calc_tax")
    assert r.risk_score < tax.risk_score


def test_ir_json_roundtrip(engine):
    from blastradius import IRDocument
    _, doc = engine
    doc2 = IRDocument.from_dict(doc.to_dict())
    assert doc2.node_ids() == doc.node_ids()
    assert len(doc2.edges) == len(doc.edges)


def test_find_partial_name(engine):
    eng, _ = engine
    assert eng.find("calc_tax") == ["app.tax.calc_tax"]
