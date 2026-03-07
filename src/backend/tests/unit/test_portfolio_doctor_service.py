from app.schemas.portfolio_doctor import PortfolioHealthMetrics
from app.services.portfolio_doctor import (
    AnalyzedHolding,
    build_alerts,
    build_summary,
    compute_category_scores,
    compute_geographic_exposure,
    compute_overlap_score,
    compute_weighted_ter,
    empty_health_response,
)


def _holding(
    asset_id: int,
    symbol: str,
    name: str,
    asset_type: str,
    weight_pct: float,
    quote_currency: str = "USD",
) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id,
        symbol=symbol,
        name=name,
        asset_type=asset_type,
        quote_currency=quote_currency,
        market_value=weight_pct * 100.0,
        weight_pct=weight_pct,
    )


def test_empty_health_response_contract():
    response = empty_health_response(123)

    assert response.portfolio_id == 123
    assert response.score == 0
    assert response.summary.risk_level == "unknown"
    assert response.metrics.geographic_exposure == {}
    assert response.metrics.portfolio_volatility is None
    assert response.category_scores.diversification == 0
    assert response.alerts == []


def test_geographic_exposure_and_overlap_follow_world_plus_us_heuristic():
    holdings = [
        _holding(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 55, "EUR"),
        _holding(2, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 30, "USD"),
        _holding(3, "EIMI", "iShares Core MSCI Emerging Markets IMI", "etf", 15, "USD"),
    ]

    exposure = compute_geographic_exposure(holdings)
    overlap_score = compute_overlap_score(holdings)
    weighted_ter = compute_weighted_ter(holdings)

    assert exposure["usa"] > 55
    assert exposure["emerging"] > 15
    assert overlap_score > 45
    assert weighted_ter is not None
    assert weighted_ter <= 0.25


def test_scoring_and_alerts_penalize_concentration_risk_and_costs():
    metrics = PortfolioHealthMetrics(
        geographic_exposure={"usa": 72.0, "europe": 8.0, "emerging": 3.0, "other": 17.0},
        max_position_weight=48.0,
        overlap_score=58.0,
        portfolio_volatility=16.4,
        weighted_ter=0.54,
    )

    category_scores = compute_category_scores(metrics, top3_weight=81.0, equity_weight=92.0)
    summary = build_summary(metrics, category_scores)
    alerts = build_alerts(metrics)

    assert category_scores.diversification < 25
    assert category_scores.risk < 25
    assert category_scores.cost_efficiency < 15
    assert summary.risk_level == "high"
    assert summary.overlap == "moderate"
    assert summary.cost_efficiency == "high_cost"
    assert {alert.type for alert in alerts} >= {
        "geographic_concentration",
        "position_concentration",
        "etf_overlap",
        "portfolio_risk",
        "high_costs",
    }
