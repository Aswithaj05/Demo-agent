"""Order report generation. Depends on calculator."""

from app.calculator import apply_discount, total_with_tax


def order_summary(price: float, discount_percent: float, tax_rate: float) -> dict:
    discounted = apply_discount(price, discount_percent)
    total = total_with_tax(discounted, tax_rate)
    return {
        "list_price": price,
        "discounted": discounted,
        "total": total,
    }
