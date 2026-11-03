"""TASK-40 / V365-010: declared volatility methodology and explainable health score.

Synthetic instruments only.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.schemas.portfolio_doctor import (
    PortfolioHealthCategoryScores,
    PortfolioHealthMetrics,
    PortfolioHealthResponse,
    PortfolioHealthSummary,
)
from app.services.portfolio_doctor import AnalyzedHolding, compute_category_scores
from app.services.portfolio_doctor._health import (
    CATEGORY_MAX_SCORES,
    compute_score_deductions,
    health_volatility_info,
)
from app.services.portfolio_doctor._stress import stress_volatility_info


def _h(asset_id, symbol, name, asset_type, weight) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency="EUR", market_value=weight * 100.0, weight_pct=weight,
    )


class _SeriesRepo:
    def __init__(self, rows):
        class _Result:
            def mappings(self):
                return self

            def all(self):
                return rows

        class _Conn:
            def execute(self, *_a, **_k):
                return _Result()

        class _Begin:
            def __enter__(self):
                return _Conn()

            def __exit__(self, *exc):
                return False

        class _Engine:
            @staticmethod
            def begin():
                return _Begin()

        self.engine = _Engine()


def _series(asset_id, closes):
    start = date.today() - timedelta(days=len(closes) + 5)
    return [
        {"asset_id": asset_id, "price_date": start + timedelta(days=i), "close": c}
        for i, c in enumerate(closes)
    ]


EQUITY = [_h(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 100)]


# --- stress volatility ----------------------------------------------------------


def test_stress_volatility_is_floored_on_a_calm_year():
    calm = _series(1, [100.0 + 0.01 * i for i in range(60)])

    sigma, info = stress_volatility_info(_SeriesRepo(calm), EQUITY)

    assert info.is_floored is True
    assert info.floor_pct == 16.0
    assert info.value_pct == 16.0
    assert sigma == pytest.approx(0.16)
    assert info.unfloored_pct is not None and info.unfloored_pct < 16.0
    assert info.period
    assert "floor" in info.method


def test_stress_volatility_not_floored_on_a_volatile_year():
    wild = _series(1, [100.0 * (1.05 if i % 2 else 0.95) ** (i % 3) for i in range(60)])

    _sigma, info = stress_volatility_info(_SeriesRepo(wild), EQUITY)

    assert info.is_floored is False
    assert info.value_pct == info.unfloored_pct
    assert info.value_pct > info.floor_pct


def test_stress_volatility_without_history_is_none():
    sigma, info = stress_volatility_info(_SeriesRepo([]), EQUITY)

    assert sigma == 0.0
    assert info.value_pct is None
    assert info.is_floored is False


def test_health_volatility_declares_its_method():
    info = health_volatility_info(12.3)

    assert info.value_pct == 12.3
    assert info.is_floored is False
    assert info.floor_pct is None
    assert "correlation" in info.method
    assert info.period


# --- score breakdown ------------------------------------------------------------


def _metrics(**overrides) -> PortfolioHealthMetrics:
    base = dict(
        geographic_exposure={"usa": 70.0, "emerging": 2.0},
        max_position_weight=65.0,
        overlap_score=55.0,
        portfolio_volatility=16.5,
        weighted_ter=0.6,
    )
    base.update(overrides)
    return PortfolioHealthMetrics(**base)


def test_deductions_explain_every_point_lost():
    metrics = _metrics()
    scores = compute_category_scores(metrics, top3_weight=90, equity_weight=90)
    deductions = compute_score_deductions(metrics, top3_weight=90, equity_weight=90)

    for category, max_score in CATEGORY_MAX_SCORES.items():
        lost = sum(d.points for d in deductions if d.category == category)
        assert getattr(scores, category) == max_score - lost, category
    codes = {d.code for d in deductions}
    assert {"usa_over_60", "volatility_over_15", "position_over_60", "top3_over_75",
            "overlap_over_50", "ter_over_0_5"} <= codes
    assert all(d.reason for d in deductions)


def test_clean_portfolio_has_no_deductions():
    metrics = _metrics(
        geographic_exposure={"usa": 40.0, "emerging": 10.0},
        max_position_weight=20.0, overlap_score=10.0, portfolio_volatility=9.0, weighted_ter=0.2,
    )
    assert compute_score_deductions(metrics, top3_weight=50, equity_weight=60) == []
    scores = compute_category_scores(metrics, top3_weight=50, equity_weight=60)
    assert sum(scores.model_dump().values()) == 100


def test_mcp_health_output_exposes_category_scores_deductions_and_volatility(monkeypatch):
    from app import copilot_tools

    metrics = _metrics()
    scores = compute_category_scores(metrics, top3_weight=90, equity_weight=90)
    deductions = compute_score_deductions(metrics, top3_weight=90, equity_weight=90)
    response = PortfolioHealthResponse(
        portfolio_id=1,
        score=sum(scores.model_dump().values()),
        summary=PortfolioHealthSummary(
            risk_level="high", diversification="moderate", overlap="high", cost_efficiency="moderate_cost",
        ),
        metrics=metrics,
        category_scores=scores,
        score_deductions=deductions,
        volatility=health_volatility_info(metrics.portfolio_volatility),
    )
    monkeypatch.setattr(copilot_tools, "analyze_portfolio_health", lambda repo, pid, uid: response)

    out = copilot_tools._get_portfolio_health({}, None, None, 1, "user")

    assert out["category_scores"] == scores.model_dump()
    assert out["category_max_scores"] == CATEGORY_MAX_SCORES
    assert len(out["score_deductions"]) == len(deductions)
    assert {"category", "code", "points", "reason"} <= set(out["score_deductions"][0])
    assert out["volatility"]["is_floored"] is False
    assert out["volatility"]["value_pct"] == 16.5
    assert out["portfolio_volatility"] == 16.5


def test_mcp_stress_output_exposes_volatility_metadata(monkeypatch):
    from app import copilot_tools
    from app.schemas.portfolio_doctor import StressTestResponse, VolatilityInfo

    info = VolatilityInfo(
        name="stress_portfolio_volatility", value_pct=16.0, method="m", period="p",
        is_floored=True, floor_pct=16.0, unfloored_pct=4.2,
    )
    monkeypatch.setattr(
        copilot_tools, "run_stress_test",
        lambda repo, pid, uid: StressTestResponse(
            portfolio_id=1, scenarios=[], portfolio_volatility_pct=16.0, volatility=info,
            analysis_date="2026-11-02",
        ),
    )

    out = copilot_tools._get_stress_test({}, None, None, 1, "user")

    assert out["portfolio_volatility_pct"] == 16.0
    assert out["volatility"]["is_floored"] is True
    assert out["volatility"]["floor_pct"] == 16.0
    assert out["volatility"]["unfloored_pct"] == 4.2


def test_empty_health_response_has_no_deductions():
    from app.services.portfolio_doctor import empty_health_response

    response = empty_health_response(1)
    assert response.score_deductions == []
    assert response.category_scores == PortfolioHealthCategoryScores()
