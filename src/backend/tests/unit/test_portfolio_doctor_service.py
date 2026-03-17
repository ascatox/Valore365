from app.schemas.portfolio_doctor import PortfolioHealthMetrics
from app.services.portfolio_doctor import (
    AnalyzedHolding,
    _build_decumulation_projections,
    _normalize_portfolio_ids,
    _rebalance_holdings_by_market_value,
    _simulate_decumulation_paths,
    _solve_sustainable_withdrawal,
    build_alerts,
    build_etf_overlap_details,
    build_position_concentration_details,
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


def test_weighted_ter_normalizes_metadata_expense_ratio_units():
    holdings = [_holding(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", "etf", 100, "USD")]

    class _Repo:
        @staticmethod
        def get_etf_enrichment_bulk(asset_ids):
            return {}

        @staticmethod
        def get_asset_metadata_bulk(asset_ids):
            return {
                1: type("Meta", (), {"expense_ratio": 0.13})(),
            }

    weighted_ter = compute_weighted_ter(holdings, repo=_Repo())

    assert weighted_ter == 0.13


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
    holdings = [
        _holding(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 48.0, "EUR"),
        _holding(2, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 28.0, "USD"),
        _holding(3, "EIMI", "iShares Core MSCI Emerging Markets IMI", "etf", 16.0, "USD"),
        _holding(4, "XNAS", "Nasdaq 100 UCITS ETF", "etf", 8.0, "USD"),
    ]
    alerts = build_alerts(metrics, holdings)

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
    position_alert = next(alert for alert in alerts if alert.type == "position_concentration")
    overlap_alert = next(alert for alert in alerts if alert.type == "etf_overlap")
    assert position_alert.details is not None
    assert position_alert.details["dominant_position"]["symbol"] == "VWCE"
    assert overlap_alert.details is not None
    assert len(overlap_alert.details["pairs"]) >= 1


def test_position_concentration_details_include_top_holdings():
    holdings = [
        _holding(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 52.5, "EUR"),
        _holding(2, "EIMI", "iShares Core MSCI Emerging Markets IMI", "etf", 21.0, "USD"),
        _holding(3, "BTP", "BTP Italia", "bond", 14.0, "EUR"),
    ]

    details = build_position_concentration_details(holdings)

    assert details is not None
    assert details["dominant_position"]["symbol"] == "VWCE"
    assert len(details["top_positions"]) == 3
    assert details["top_positions"][0]["weight_pct"] == 52.5


def test_etf_overlap_details_return_top_pairs():
    holdings = [
        _holding(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 45.0, "EUR"),
        _holding(2, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 35.0, "USD"),
        _holding(3, "EQQQ", "Invesco Nasdaq 100 UCITS ETF", "etf", 20.0, "USD"),
    ]

    details = build_etf_overlap_details(holdings, 63.4)

    assert details is not None
    assert details["overlap_score"] == 63.4
    assert len(details["pairs"]) >= 1
    first_pair = details["pairs"][0]
    assert first_pair["left"]["symbol"] in {"VWCE", "CSPX", "EQQQ"}
    assert first_pair["estimated_overlap_pct"] >= 40


def test_sustainable_withdrawal_stays_positive_with_real_return():
    sustainable = _solve_sustainable_withdrawal(
        initial_capital=1_000_000,
        years=30,
        annual_return_pct=5.0,
        inflation_rate_pct=2.0,
        other_income_annual=10_000,
    )

    assert sustainable > 0
    assert sustainable > 10_000


def test_decumulation_paths_deplete_with_zero_return_and_high_withdrawals():
    paths = _simulate_decumulation_paths(
        initial_capital=100_000,
        annual_withdrawal=30_000,
        years=5,
        inflation_rate_pct=0.0,
        other_income_annual=0.0,
        mu_annual=0.0,
        sigma_annual=0.0,
    )

    projections = _build_decumulation_projections(
        paths=paths,
        years=5,
        annual_withdrawal=30_000,
        inflation_rate_pct=0.0,
        other_income_annual=0.0,
        current_age=50,
    )

    assert projections[0].p50_ending_capital == 70000
    assert projections[3].p50_ending_capital == 0
    assert projections[3].depletion_probability_pct == 100


def test_normalize_portfolio_ids_deduplicates_and_discards_invalid_values():
    normalized = _normalize_portfolio_ids([3, 0, 3, -4, 5, 7, 5])

    assert normalized == [3, 5, 7]


def test_rebalance_holdings_by_market_value_reweights_across_portfolios():
    holdings = [
      _holding(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 60.0, "EUR"),
      _holding(2, "BOND", "Global Aggregate Bond", "bond", 40.0, "EUR"),
      _holding(3, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 100.0, "USD"),
    ]

    rebalanced = _rebalance_holdings_by_market_value(holdings)

    assert len(rebalanced) == 3
    total_weight = sum(holding.weight_pct for holding in rebalanced)
    assert round(total_weight, 6) == 100.0
    assert round(rebalanced[0].weight_pct, 1) == 30.0
    assert round(rebalanced[1].weight_pct, 1) == 20.0
    assert round(rebalanced[2].weight_pct, 1) == 50.0
