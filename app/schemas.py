from datetime import datetime

from pydantic import BaseModel, Field


class OrderItemInput(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    qty: int = Field(gt=0, le=2_147_483_647)


class OrderCreate(BaseModel):
    order_ref: str = Field(min_length=1, max_length=200)
    customer_id: str = Field(min_length=1, max_length=200)
    items: list[OrderItemInput] = Field(..., min_items=1, max_items=100)


class ItemView(BaseModel):
    sku: str
    qty: int
    unit_price_cents: int
    line_total_cents: int


class OrderView(BaseModel):
    id: str
    order_ref: str
    customer_id: str
    total_cents: int
    status: str
    created_at: datetime
    items: list[ItemView]


class OrderAccepted(BaseModel):
    order_id: str
    order_ref: str
    total_cents: int
    status: str
    duplicate: bool = False
