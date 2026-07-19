"""Pricing calculations."""


def add(a: float, b: float) -> float:
    return a + b


def apply_discount(price: float, percent: float) -> float:
    """Apply a percentage discount to a price."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (1 - percent / 100), 2)


def total_with_tax(price: float, tax_rate: float) -> float:
    """Add tax to a price."""
    return round(price * (1 + tax_rate), 2)
