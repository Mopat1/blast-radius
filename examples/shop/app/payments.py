from app.cart import cart_total

def charge(items: list[float]) -> dict:
    total = cart_total(items)
    return {"status": "charged", "amount": total}

def refund(order_id: str) -> dict:
    return {"status": "refunded", "order": order_id}
