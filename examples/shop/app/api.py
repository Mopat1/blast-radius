from fastapi import FastAPI
from app.payments import charge, refund

app = FastAPI()

@app.post("/checkout")
def checkout(items: list[float]):
    return charge(items)

@app.post("/refund/{order_id}")
def do_refund(order_id: str):
    return refund(order_id)
