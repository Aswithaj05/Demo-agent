import pytest

from app.calculator import add, apply_discount, total_with_tax


def test_add():
    assert add(2, 3) == 5


def test_apply_discount_basic():
    assert apply_discount(100.0, 25) == 75.0


def test_apply_discount_zero():
    assert apply_discount(50.0, 0) == 50.0


def test_apply_discount_invalid():
    with pytest.raises(ValueError):
        apply_discount(50.0, 150)


def test_total_with_tax():
    assert total_with_tax(100.0, 0.08) == 108.0
