"""TASK-88: la tabella posizioni e il what-if usano lo scostamento di `get_target_drift`.

- `GET /portfolios/{id}/target-drift` (letto dalla tabella posizioni) restituisce gli stessi
  valori del tool Copilot/MCP `get_target_drift`, dalla stessa funzione
  (`services.rebalance.target_drift_rows`), con verifica di proprietà (404).
- `calculate_what_if` misura `old_drift`/`new_drift` sulla stessa base (strumenti con target +
  liquidità), mentre `old_weight`/`new_weight` restano sulle sole posizioni (concentrazione).

Caso del portafoglio 9101 del seed dell'Auditor: 70.000 / 20.000 / 10.000 €, liquidità
9.256,50 €, target 50/40/10.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.copilot_tools as copilot_tools
from app.api.routes_rebalancing import register_rebalancing_routes
from app.auth import AuthContext
from app.errors import AppError
from app.rate_limit import require_auth_rate_limited
from tests.unit.test_copilot_target_weights import CASH, EXPECTED, PID, TOTAL, make_repo

USER = "u"


def _client(repo: MagicMock, *, enabled: bool = True) -> TestClient:
    def _ensure() -> None:
        if not enabled:
            raise AppError(code="feature_disabled", message="off", status_code=404)

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_rebalancing_routes(
        router, repo, settings=MagicMock(), finance_client=MagicMock(), historical_service=MagicMock(),
        ensure_target_allocation_enabled=_ensure,
    )
    app.include_router(router)


    @app.exception_handler(AppError)
    async def _handler(_: Request, exc: AppError) -> JSONResponse:  # same body as app.main
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id=USER)
    return TestClient(app)


def _tool(name: str, args: dict, repo: MagicMock) -> dict:
    return copilot_tools.execute_tool(name, args, repo, MagicMock(), PID, USER)


def test_route_returns_the_values_of_get_target_drift():
    repo = make_repo()
    body = _client(repo).get(f"/api/portfolios/{PID}/target-drift").json()
    tool = _tool("get_target_drift", {}, repo)

    assert body["total_value"] == tool["total_value"] == TOTAL
    assert body["cash_balance"] == tool["cash_balance"] == CASH
    assert body["weight_basis_note"] == tool["weight_basis_note"]
    assert [
        (i["symbol"], i["current_weight_pct"], i["target_weight_pct"], i["drift_pct"], i["market_value"])
        for i in body["items"]
    ] == [
        (d["symbol"], d["current_weight"], d["target_weight"], d["drift"], d["market_value"])
        for d in tool["drift"]
    ]
    by = {i["symbol"]: i for i in body["items"]}
    assert {s: i["current_weight_pct"] for s, i in by.items()} == EXPECTED
    # AUDTECH.DE: 10,0 % delle posizioni («in linea» nella tabella di prima), 0,85 pt sotto target qui.
    assert by["AUDTECH.DE"]["drift_pct"] == -0.85
    assert all(isinstance(i["asset_id"], int) for i in body["items"])
    repo.list_portfolio_target_allocations.assert_called_with(PID, USER)


def test_route_untargeted_holding_out_of_the_base():
    repo = make_repo(extra_positions={"AUDOUT.MI": 5000.0})
    body = _client(repo).get(f"/api/portfolios/{PID}/target-drift").json()
    assert body["total_value"] == TOTAL
    assert body["untargeted_holdings"] == ["AUDOUT.MI"]
    assert "AUDOUT.MI" not in {i["symbol"] for i in body["items"]}


def test_route_without_targets_is_empty():
    repo = make_repo(targets={})
    body = _client(repo).get(f"/api/portfolios/{PID}/target-drift").json()
    assert body["items"] == [] and body["total_value"] == 0.0
    repo.get_positions.assert_not_called()


def test_route_checks_ownership():
    repo = make_repo()
    repo.list_portfolio_target_allocations.side_effect = ValueError("Portfolio non trovato")
    resp = _client(repo).get(f"/api/portfolios/{PID}/target-drift")
    assert resp.status_code == 404
    repo.get_positions.assert_not_called()


def test_route_respects_feature_flag():
    resp = _client(make_repo(), enabled=False).get(f"/api/portfolios/{PID}/target-drift")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# calculate_what_if
# ---------------------------------------------------------------------------


def test_what_if_old_drift_equals_get_target_drift():
    repo = make_repo()
    drift = {d["symbol"]: d for d in _tool("get_target_drift", {}, repo)["drift"]}
    for symbol in EXPECTED:
        res = _tool("calculate_what_if", {"action": "buy", "symbol": symbol, "amount_eur": 1000.0}, repo)
        assert res["old_drift"] == drift[symbol]["drift"]
        assert res["target_basis"]["current_weight_before"] == drift[symbol]["current_weight"]
        assert res["target_basis"]["total_value_before"] == TOTAL
    # Prima: AUDTECH.DE in linea (10,0 − 10).
    tech = _tool("calculate_what_if", {"action": "buy", "symbol": "AUDTECH.DE", "amount_eur": 1000.0}, repo)
    assert tech["old_drift"] == -0.85
    assert tech["old_weight"] == 10.0  # concentrazione: peso sulle sole posizioni, invariato


def test_what_if_buy_is_paid_from_cash():
    repo = make_repo()
    res = _tool("calculate_what_if", {"action": "buy", "symbol": "AUDTECH.DE", "amount_eur": 1000.0}, repo)
    # Base invariata (liquidità − 1000, strumento + 1000): 11.000 / 109.256,50.
    assert res["target_basis"]["total_value_after"] == TOTAL
    assert res["target_basis"]["cash_after"] == round(CASH - 1000.0, 2)
    assert res["new_drift"] == round(11000.0 / TOTAL * 100 - 10.0, 2)
    # Pesi della concentrazione sulle sole posizioni, come prima.
    assert res["new_weight"] == round(11000.0 / 101000.0 * 100, 2)


def test_what_if_buy_beyond_cash_adds_to_the_base():
    repo = make_repo()
    amount = 20000.0
    res = _tool("calculate_what_if", {"action": "buy", "symbol": "AUDBD.MI", "amount_eur": amount}, repo)
    base_after = 100000.0 + amount  # liquidità esaurita: la parte oltre il saldo è un nuovo versamento
    assert res["target_basis"]["total_value_after"] == base_after
    assert res["target_basis"]["cash_after"] == 0.0
    assert res["new_drift"] == round((20000.0 + amount) / base_after * 100 - 40.0, 2)


def test_what_if_sell_keeps_proceeds_in_cash():
    repo = make_repo()
    res = _tool("calculate_what_if", {"action": "sell", "symbol": "AUDEQ.MI", "amount_eur": 10000.0}, repo)
    assert res["target_basis"]["total_value_after"] == TOTAL
    assert res["new_drift"] == round(60000.0 / TOTAL * 100 - 50.0, 2)
    assert res["old_drift"] == round(70000.0 / TOTAL * 100 - 50.0, 2)


def test_what_if_untargeted_symbol_has_no_drift():
    repo = make_repo(extra_positions={"AUDOUT.MI": 5000.0})
    res = _tool("calculate_what_if", {"action": "buy", "symbol": "AUDOUT.MI", "amount_eur": 1000.0}, repo)
    assert res["old_drift"] is None and res["new_drift"] is None and res["target_basis"] is None
    assert res["weight_basis_note"]


def test_what_if_new_targeted_asset_not_held():
    repo = make_repo(values={"AUDEQ.MI": 70000.0, "AUDBD.MI": 20000.0})
    res = _tool("calculate_what_if", {"action": "buy", "symbol": "AUDTECH.DE", "amount_eur": 1000.0}, repo)
    base = 90000.0 + CASH
    assert res["old_drift"] == -10.0
    assert res["new_drift"] == pytest.approx(round(1000.0 / base * 100 - 10.0, 2))
