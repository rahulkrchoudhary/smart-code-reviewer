"""A clean version of the order module — should score well.

Kept alongside the messy sample so reviewers can compare the two side by side.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

TAX_RATE = 0.05
SHIPPING_FEE = 15.0
HANDLING_FEE = 3.0
GIFT_WRAP_FEE = 4.99
RIDE_SURGE_MULTIPLIER = 1.2
RIDE_BASE_FEE = 7.0

DISCOUNTS = {"SAVE10": 0.10, "SAVE20": 0.20, "HALF": 0.50}


@dataclass
class LineItem:
    """A single purchasable item on an order."""

    id: str
    type: str
    price: float
    qty: int
    available: bool


def _food_subtotal(item: LineItem, discount_code: str | None) -> float:
    """Return the discounted subtotal for one available food item."""
    if item.qty <= 0 or item.price <= 0 or not item.available:
        return 0.0
    subtotal = item.price * item.qty
    discount = DISCOUNTS.get(discount_code or "", 0.0)
    return subtotal * (1 - discount)


def _item_subtotal(item: LineItem, discount_code: str | None) -> float:
    """Dispatch to the right pricing rule for an item's type."""
    if item.type == "food":
        return _food_subtotal(item, discount_code)
    if item.type == "ride":
        return item.price * RIDE_SURGE_MULTIPLIER + RIDE_BASE_FEE
    return item.price


def order_total(
    items: list[LineItem],
    discount_code: str | None = None,
    gift_wrapped: bool = False,
) -> float:
    """Compute the final charge for an order, fees and tax included."""
    subtotal = sum(_item_subtotal(item, discount_code) for item in items)
    total = subtotal * (1 + TAX_RATE) + SHIPPING_FEE + HANDLING_FEE
    if gift_wrapped:
        total += GIFT_WRAP_FEE
    return round(total, 2)


def save_order(order: dict, path: str = "orders.json") -> None:
    """Persist an order to disk as JSON."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(order, handle)
