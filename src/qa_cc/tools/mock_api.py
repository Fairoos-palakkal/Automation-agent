"""FastAPI Mock Backend for Own Site (Phase 2.6).

Serves mock REST endpoints for Acme Store with planted defects (D3).
Defects correspond to benchmark/ground_truth/defects.json:
- DEFECT-001: Missing email validation on contact form/endpoint
- DEFECT-004: Cart quantity allows negative values
- DEFECT-007: Promo code application allows negative balance
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import FastAPI
from pydantic import BaseModel


PLANTED_API_DEFECTS: List[str] = [
    "DEFECT-001",
    "DEFECT-004",
    "DEFECT-007",
]

app = FastAPI(title="Acme Store Mock Backend")


class ContactRequest(BaseModel):
    name: str
    email: str
    message: Optional[str] = ""


class CartUpdateRequest(BaseModel):
    item_id: str
    quantity: int


class PromoRequest(BaseModel):
    code: str
    total: float = 50.0


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cart")
def get_cart() -> Dict[str, Any]:
    return {
        "items": [
            {"id": "widget-1", "name": "Acme Widget Pro", "price": 50.0, "quantity": 1}
        ],
        "total": 50.0,
    }


@app.post("/api/contact")
def submit_contact(req: ContactRequest) -> Dict[str, Any]:
    # DEFECT-001: No email format validation (accepts invalid email string without 400/422)
    return {
        "success": True,
        "message": f"Message received from {req.name}",
        "email_recorded": req.email,
    }


@app.post("/api/cart/update")
def update_cart(req: CartUpdateRequest) -> Dict[str, Any]:
    # DEFECT-004: Allows negative quantity and computes negative cart total
    unit_price = 50.0
    new_total = req.quantity * unit_price
    return {
        "item_id": req.item_id,
        "quantity": req.quantity,
        "unit_price": unit_price,
        "total": new_total,
    }


@app.post("/api/cart/apply-promo")
def apply_promo(req: PromoRequest) -> Dict[str, Any]:
    # DEFECT-007: Re-applying discount allows balance to drop below 0 without floor
    discount = 20.0 if req.code.strip().upper() == "SAVE20" else 0.0
    new_total = req.total - discount
    return {
        "code": req.code,
        "discount": discount,
        "new_total": new_total,
    }
