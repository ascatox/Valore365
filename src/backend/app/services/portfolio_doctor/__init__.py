"""Portfolio Doctor service package.

Re-exports the public API so that external imports remain unchanged:
    from app.services.portfolio_doctor import analyze_portfolio_health, ...
"""

from ._holdings import (
    AnalyzedHolding,
    _normalize_portfolio_ids,
    _rebalance_holdings_by_market_value,
)
from ._health import (
    analyze_portfolio_health,
    build_alerts,
    build_etf_overlap_details,
    build_position_concentration_details,
    build_suggestions,
    build_summary,
    compute_category_scores,
    compute_geographic_exposure,
    compute_max_position_weight,
    compute_overlap_score,
    compute_total_score,
    compute_weighted_ter,
    empty_health_response,
)
from ._stress import run_stress_test
from ._monte_carlo import (
    run_monte_carlo_projection,
    run_decumulation_plan,
    run_aggregate_decumulation_plan,
    _build_decumulation_projections,
    _simulate_decumulation_paths,
    _solve_sustainable_withdrawal,
)
from ._xray import compute_portfolio_xray

__all__ = [
    "AnalyzedHolding",
    "_normalize_portfolio_ids",
    "_rebalance_holdings_by_market_value",
    "analyze_portfolio_health",
    "build_alerts",
    "build_etf_overlap_details",
    "build_position_concentration_details",
    "build_suggestions",
    "build_summary",
    "compute_category_scores",
    "compute_geographic_exposure",
    "compute_max_position_weight",
    "compute_overlap_score",
    "compute_total_score",
    "compute_weighted_ter",
    "empty_health_response",
    "run_stress_test",
    "run_monte_carlo_projection",
    "run_decumulation_plan",
    "run_aggregate_decumulation_plan",
    "_build_decumulation_projections",
    "_simulate_decumulation_paths",
    "_solve_sustainable_withdrawal",
    "compute_portfolio_xray",
]
