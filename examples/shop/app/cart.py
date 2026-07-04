from app.tax import calc_tax

def cart_total(items: list[float]) -> float:
    subtotal = sum(items)
    return subtotal + calc_tax(subtotal)
