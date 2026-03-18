from datetime import date

from app.repository._utilities import _build_cash_breakdown, _compute_cash_balance_base


def test_build_cash_breakdown_includes_opening_cash_in_base_currency():
    breakdown = _build_cash_breakdown(
        base_currency="EUR",
        opening_cash_balance=5000.0,
        rows=[
            {"trade_currency": "EUR", "balance": -1200.0},
            {"trade_currency": "USD", "balance": 300.0},
        ],
    )

    assert [(item.currency, item.balance) for item in breakdown] == [
        ("EUR", 3800.0),
        ("USD", 300.0),
    ]


def test_build_cash_breakdown_creates_base_currency_row_when_only_opening_cash_exists():
    breakdown = _build_cash_breakdown(
        base_currency="EUR",
        opening_cash_balance=2500.0,
        rows=[],
    )

    assert [(item.currency, item.balance) for item in breakdown] == [("EUR", 2500.0)]


def test_compute_cash_balance_base_only_cash_movements():
    """Cash is only affected by explicit cash movements (deposit/withdrawal/dividend/fee/interest).
    Buy/sell transactions do NOT affect the cash balance."""
    total = _compute_cash_balance_base(
        base_currency="EUR",
        opening_cash_balance=0.0,
        rows=[
            {
                "side": "buy",
                "trade_date": date(2026, 1, 2),
                "quantity": 20.0,
                "price": 100.0,
                "fees": 5.0,
                "taxes": 0.0,
                "trade_currency": "EUR",
            },
            {
                "side": "deposit",
                "trade_date": date(2026, 1, 3),
                "quantity": 500.0,
                "price": 1.0,
                "fees": 0.0,
                "taxes": 0.0,
                "trade_currency": "EUR",
            },
            {
                "side": "sell",
                "trade_date": date(2026, 1, 4),
                "quantity": 2.0,
                "price": 120.0,
                "fees": 1.0,
                "taxes": 0.0,
                "trade_currency": "USD",
            },
            {
                "side": "withdrawal",
                "trade_date": date(2026, 1, 5),
                "quantity": 100.0,
                "price": 1.0,
                "fees": 0.0,
                "taxes": 0.0,
                "trade_currency": "EUR",
            },
        ],
        fx_rows=[
            {
                "from_ccy": "USD",
                "price_date": date(2026, 1, 4),
                "rate": 0.9,
            }
        ],
    )

    # Only deposit (500) - withdrawal (100) = 400. Buy/sell ignored.
    assert total == 400.0
