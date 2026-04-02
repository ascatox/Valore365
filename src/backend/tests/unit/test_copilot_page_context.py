from types import SimpleNamespace

import app.copilot.snapshot as snapshot_module
from app.copilot.snapshot import build_portfolio_snapshot_light
from app.copilot_tools import format_tools_for_provider, get_allowed_tool_names_for_page_context


class _FakePerformanceService:
    def __init__(self, repo):
        self.repo = repo

    def get_performance_summary(self, portfolio_id: int, user_id: str, period: str):
        return SimpleNamespace(twr=SimpleNamespace(twr_pct=12.34))


class _FakeRepo:
    def get_summary(self, portfolio_id: int, user_id: str):
        return SimpleNamespace(
            base_currency="EUR",
            market_value=10000.0,
            cost_basis=8000.0,
            unrealized_pl=2000.0,
            unrealized_pl_pct=25.0,
            day_change=120.0,
            day_change_pct=1.2,
            cash_balance=500.0,
        )

    def get_positions(self, portfolio_id: int, user_id: str):
        return [
            SimpleNamespace(
                asset_id=1,
                symbol="VWCE",
                name="Vanguard FTSE All-World",
                weight=60.0,
                market_value=6000.0,
                unrealized_pl_pct=10.0,
                day_change_pct=0.5,
            ),
            SimpleNamespace(
                asset_id=2,
                symbol="AGGH",
                name="iShares Core Global Aggregate Bond",
                weight=40.0,
                market_value=4000.0,
                unrealized_pl_pct=4.0,
                day_change_pct=0.1,
            ),
        ]

    def get_allocation(self, portfolio_id: int, user_id: str):
        return [
            SimpleNamespace(asset_id=1, weight_pct=60.0),
            SimpleNamespace(asset_id=2, weight_pct=40.0),
        ]

    def list_portfolio_target_allocations(self, portfolio_id: int, user_id: str):
        return [
            SimpleNamespace(asset_id=1, symbol="VWCE", weight_pct=70.0),
            SimpleNamespace(asset_id=2, symbol="AGGH", weight_pct=30.0),
        ]

    def list_portfolios(self, user_id: str):
        return [SimpleNamespace(id=1, name="Core Portfolio")]

    def get_user_settings(self, user_id: str):
        return SimpleNamespace(
            fire_annual_expenses=24000.0,
            fire_annual_contribution=12000.0,
            fire_expected_return_pct=5.0,
            fire_safe_withdrawal_rate=4.0,
            fire_capital_gains_tax_rate=26.0,
            fire_current_age=35,
            fire_target_age=50,
        )

    def list_pac_rules(self, portfolio_id: int, user_id: str):
        return [
            SimpleNamespace(
                active=True,
                symbol="VWCE",
                asset_name="Vanguard FTSE All-World",
                mode="amount",
                amount=300.0,
                quantity=None,
                frequency="monthly",
                day_of_month=5,
                day_of_week=None,
                start_date="2026-01-01",
                end_date=None,
            )
        ]

    def list_pending_pac_executions(self, portfolio_id: int, user_id: str):
        return [SimpleNamespace(id=1)]


def test_dashboard_snapshot_stays_page_scoped(monkeypatch):
    monkeypatch.setattr("app.services.performance_service.PerformanceService", _FakePerformanceService)
    monkeypatch.setattr(snapshot_module, "_load_holdings", lambda repo, portfolio_id, user_id: ["holding"])
    monkeypatch.setattr(snapshot_module, "compute_weighted_ter", lambda holdings, repo: 0.22)

    snapshot = build_portfolio_snapshot_light(_FakeRepo(), 1, "user-1", page_context="dashboard")

    assert "positions" in snapshot
    assert "target_drift" in snapshot
    assert "performance" in snapshot
    assert "fire" not in snapshot
    assert "pac_plans" not in snapshot
    assert snapshot["portfolio"].get("weighted_ter_pct") is None


def test_fire_snapshot_includes_fire_but_not_target_or_pac(monkeypatch):
    monkeypatch.setattr("app.services.performance_service.PerformanceService", _FakePerformanceService)
    monkeypatch.setattr(snapshot_module, "_load_holdings", lambda repo, portfolio_id, user_id: ["holding"])
    monkeypatch.setattr(snapshot_module, "compute_weighted_ter", lambda holdings, repo: 0.22)

    snapshot = build_portfolio_snapshot_light(_FakeRepo(), 1, "user-1", page_context="fire")

    assert "fire" in snapshot
    assert "performance" in snapshot
    assert "target_drift" not in snapshot
    assert "pac_plans" not in snapshot
    assert snapshot["portfolio"].get("weighted_ter_pct") is None


def test_page_context_filters_available_tools():
    dashboard_tools = format_tools_for_provider(
        "openai",
        allowed_tool_names=get_allowed_tool_names_for_page_context("dashboard"),
    )
    fire_tools = format_tools_for_provider(
        "openai",
        allowed_tool_names=get_allowed_tool_names_for_page_context("fire"),
    )

    dashboard_names = {tool["function"]["name"] for tool in dashboard_tools}
    fire_names = {tool["function"]["name"] for tool in fire_tools}

    assert "get_monte_carlo" not in dashboard_names
    assert "get_monte_carlo" in fire_names
    assert "get_day_movers" in dashboard_names
