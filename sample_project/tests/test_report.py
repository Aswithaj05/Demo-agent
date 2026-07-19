from app.report import order_summary


def test_order_summary():
    result = order_summary(200.0, 10, 0.05)
    assert result["list_price"] == 200.0
    assert result["discounted"] == 180.0
    assert result["total"] == 189.0


def test_order_summary_no_discount():
    result = order_summary(100.0, 0, 0.0)
    assert result["total"] == 100.0
