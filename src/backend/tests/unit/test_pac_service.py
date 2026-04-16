from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.services.pac_service import PacExecutionService


class _FakeRepo:
    def __init__(self, *, base_currency: str = "EUR", available_cash: float = 0.0) -> None:
        self.base_currency = base_currency
        self.available_cash = available_cash
        self.created_payload = None
        self.confirmed = None

    def get_portfolio_base_currency(self, portfolio_id: int, user_id: str) -> str:
        return self.base_currency

    def get_current_cash_balance_value(self, portfolio_id: int, user_id: str) -> float:
        return self.available_cash

    def create_transaction(self, payload, user_id: str):
        self.created_payload = payload
        return SimpleNamespace(id=987)

    def confirm_pac_execution(self, execution_id: int, transaction_id: int, price: float, quantity: float, user_id: str) -> None:
        self.confirmed = (execution_id, transaction_id, price, quantity, user_id)


class _TestPacExecutionService(PacExecutionService):
    def __init__(self, repo: _FakeRepo, *, latest_price: float, fx_rate: float = 1.0) -> None:
        self._latest_price = latest_price
        self._fx_rate = fx_rate
        super().__init__(engine=None, repo=repo)  # type: ignore[arg-type]

    def _get_latest_price(self, asset_id: int, target_date: date) -> float:
        return self._latest_price

    def _get_fx_rate_on_or_before(self, from_currency: str, to_currency: str, target_date: date) -> float:
        return self._fx_rate


def test_auto_execute_pending_execution_creates_transaction_from_amount_rule():
    repo = _FakeRepo(available_cash=500.0)
    service = _TestPacExecutionService(repo, latest_price=25.0)

    service._auto_execute_pending_execution(
        {
            "id": 11,
            "portfolio_id": 5,
            "asset_id": 9,
            "mode": "amount",
            "amount": 100.0,
            "quantity": None,
            "owner_user_id": "user-1",
            "scheduled_date": date(2026, 4, 15),
            "quote_currency": "EUR",
        }
    )

    assert repo.created_payload is not None
    assert repo.created_payload.portfolio_id == 5
    assert repo.created_payload.asset_id == 9
    assert repo.created_payload.side == "buy"
    assert repo.created_payload.trade_at == datetime(2026, 4, 15, 0, 0, 0)
    assert repo.created_payload.quantity == 4.0
    assert repo.created_payload.price == 25.0
    assert repo.created_payload.trade_currency == "EUR"
    assert repo.confirmed == (11, 987, 25.0, 4.0, "user-1")


def test_auto_execute_pending_execution_fails_when_cash_is_insufficient():
    repo = _FakeRepo(base_currency="EUR", available_cash=80.0)
    service = _TestPacExecutionService(repo, latest_price=25.0, fx_rate=1.0)

    with pytest.raises(ValueError, match="Liquidita insufficiente"):
        service._auto_execute_pending_execution(
            {
                "id": 12,
                "portfolio_id": 5,
                "asset_id": 9,
                "mode": "quantity",
                "amount": None,
                "quantity": 4.0,
                "owner_user_id": "user-1",
                "scheduled_date": date(2026, 4, 15),
                "quote_currency": "EUR",
            }
        )

    assert repo.created_payload is None
    assert repo.confirmed is None
