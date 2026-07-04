from app.payments import charge, refund
from app.tax import calc_tax

def test_charge():
    assert charge([100.0])["status"] == "charged"

def test_refund():
    assert refund("o1")["status"] == "refunded"

def test_tax():
    assert calc_tax(100) == 18.0
