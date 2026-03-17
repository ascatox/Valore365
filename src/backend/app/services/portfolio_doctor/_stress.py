import logging
import math
from collections import defaultdict
from datetime import date

from sqlalchemy import text

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    StressTestAssetImpact,
    StressTestResponse,
    StressTestScenarioResult,
)
from ...constants.stress_scenarios import HISTORICAL_SCENARIOS, SHOCK_SCENARIOS
from ._holdings import AnalyzedHolding, _load_holdings, _compute_portfolio_return_params

logger = logging.getLogger(__name__)


def _classify_risk_level(impact_pct: float) -> str:
    abs_impact = abs(impact_pct)
    if abs_impact < 5:
        return "low"
    if abs_impact < 15:
        return "medium"
    if abs_impact < 30:
        return "high"
    return "critical"


def _compute_historical_scenario(
    repo: PortfolioRepository,
    holdings: list[AnalyzedHolding],
    scenario: dict,
) -> StressTestScenarioResult:
    """Compute portfolio impact during a historical scenario using price_bars_1d."""
    start_date = date.fromisoformat(scenario["start"])
    end_date = date.fromisoformat(scenario["end"])
    asset_ids = [h.asset_id for h in holdings if h.asset_type != "cash"]

    prices_by_asset: dict[int, list[tuple[date, float]]] = defaultdict(list)
    if asset_ids:
        with repo.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select asset_id, price_date, close::float8 as close
                    from price_bars_1d
                    where asset_id = any(:asset_ids)
                      and price_date >= :start_date
                      and price_date <= :end_date
                    order by asset_id asc, price_date asc
                    """
                ),
                {"asset_ids": asset_ids, "start_date": start_date, "end_date": end_date},
            ).mappings().all()
        for row in rows:
            close = float(row["close"])
            if close > 0 and math.isfinite(close):
                prices_by_asset[int(row["asset_id"])].append(
                    (row["price_date"], close)
                )

    weighted_return = 0.0
    covered_weight = 0.0
    asset_impacts: list[StressTestAssetImpact] = []

    for holding in holdings:
        if holding.asset_type == "cash":
            continue
        series = prices_by_asset.get(holding.asset_id, [])
        if len(series) < 2:
            continue
        first_price = series[0][1]
        last_price = series[-1][1]
        asset_return = (last_price - first_price) / first_price
        weight_fraction = holding.weight_pct / 100.0
        weighted_return += asset_return * weight_fraction
        covered_weight += weight_fraction
        asset_impacts.append(
            StressTestAssetImpact(
                symbol=holding.symbol,
                name=holding.name,
                weight_pct=round(holding.weight_pct, 2),
                estimated_loss_pct=round(asset_return * 100, 2),
            )
        )

    if covered_weight > 0:
        # Keep uncovered weight in the portfolio with a neutral impact instead
        # of renormalizing losses to the subset that has historical prices.
        portfolio_impact = weighted_return * 100.0
    else:
        # Fallback: estimate from benchmark drawdown scaled by portfolio beta
        portfolio_impact = scenario["benchmark_drawdown"] * 0.8

    # Compute max drawdown from portfolio-weighted daily series
    max_dd = _compute_weighted_drawdown(prices_by_asset, holdings) if covered_weight > 0 else portfolio_impact

    # Estimate recovery months (rough heuristic based on drawdown depth)
    recovery_months = None
    if max_dd < 0:
        recovery_months = max(1, int(abs(max_dd) / 2.5))

    asset_impacts.sort(key=lambda a: a.estimated_loss_pct)
    most_impacted = asset_impacts[:5]

    return StressTestScenarioResult(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        scenario_type="historical",
        period=scenario["period"],
        estimated_portfolio_impact_pct=round(portfolio_impact, 2),
        max_drawdown_pct=round(max_dd, 2),
        recovery_months=recovery_months,
        benchmark_drawdown_pct=scenario["benchmark_drawdown"],
        risk_level=_classify_risk_level(portfolio_impact),
        most_impacted_assets=most_impacted,
    )


def _compute_weighted_drawdown(
    prices_by_asset: dict[int, list[tuple[date, float]]],
    holdings: list[AnalyzedHolding],
) -> float:
    """Compute portfolio-level max drawdown from per-asset daily prices."""
    # Collect all unique dates
    all_dates: set[date] = set()
    for series in prices_by_asset.values():
        for d, _ in series:
            all_dates.add(d)
    if not all_dates:
        return 0.0

    sorted_dates = sorted(all_dates)
    # Build price lookup per asset
    price_lookup: dict[int, dict[date, float]] = {}
    for asset_id, series in prices_by_asset.items():
        price_lookup[asset_id] = {d: p for d, p in series}

    weight_map = {h.asset_id: h.weight_pct / 100.0 for h in holdings}
    total_weight = sum(weight_map.values())
    if total_weight <= 0:
        return 0.0

    # Compute normalized portfolio value per date
    portfolio_values: list[float] = []
    for d in sorted_dates:
        value = 0.0
        for asset_id, w in weight_map.items():
            lookup = price_lookup.get(asset_id, {})
            series = prices_by_asset.get(asset_id, [])
            if series:
                first_price = series[0][1]
                latest_price = first_price
                for series_date, series_price in series:
                    if series_date > d:
                        break
                    latest_price = series_price
                normalized_value = latest_price / first_price if first_price > 0 else 1.0
            else:
                # Cash and uncovered assets are held flat in the stress path
                # instead of being dropped from the portfolio.
                normalized_value = 1.0
            value += normalized_value * (w / total_weight)
        if value > 0:
            portfolio_values.append(value)

    if len(portfolio_values) < 2:
        return 0.0

    peak = portfolio_values[0]
    max_dd = 0.0
    for v in portfolio_values[1:]:
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100.0
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _compute_shock_scenario(
    holdings: list[AnalyzedHolding],
    scenario: dict,
) -> StressTestScenarioResult:
    """Apply synthetic shocks to asset classes and compute portfolio impact."""
    shocks = scenario["shocks"]
    tech_mult = scenario.get("tech_multiplier", 1.0)
    commodity_mult = scenario.get("commodity_multiplier", 1.0)

    weighted_impact = 0.0
    covered_weight = 0.0
    asset_impacts: list[StressTestAssetImpact] = []

    for holding in holdings:
        asset_class = _shock_asset_class(holding)
        base_shock = shocks.get(asset_class, shocks.get("equity", -0.10))

        # Apply multipliers for specific scenarios
        multiplier = 1.0
        name_lower = holding.name.lower()
        symbol_lower = holding.symbol.lower()
        if tech_mult != 1.0 and _is_tech_like(name_lower, symbol_lower):
            multiplier = tech_mult
        if commodity_mult != 1.0 and _is_commodity_like(name_lower, symbol_lower):
            multiplier = commodity_mult

        asset_shock = base_shock * multiplier
        weight_fraction = holding.weight_pct / 100.0
        weighted_impact += asset_shock * weight_fraction
        covered_weight += weight_fraction

        asset_impacts.append(
            StressTestAssetImpact(
                symbol=holding.symbol,
                name=holding.name,
                weight_pct=round(holding.weight_pct, 2),
                estimated_loss_pct=round(asset_shock * 100, 2),
            )
        )

    portfolio_impact = (weighted_impact / covered_weight * 100.0) if covered_weight > 0 else 0.0

    asset_impacts.sort(key=lambda a: a.estimated_loss_pct)
    most_impacted = asset_impacts[:5]

    return StressTestScenarioResult(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        scenario_type="shock",
        period=None,
        estimated_portfolio_impact_pct=round(portfolio_impact, 2),
        max_drawdown_pct=round(portfolio_impact, 2),
        recovery_months=None,
        benchmark_drawdown_pct=None,
        risk_level=_classify_risk_level(portfolio_impact),
        most_impacted_assets=most_impacted,
    )


def _shock_asset_class(holding: AnalyzedHolding) -> str:
    """Map a holding to a broad asset class for shock scenarios."""
    at = holding.asset_type.lower()
    if at == "cash":
        return "cash"
    if at == "bond":
        return "bond"
    name_lower = holding.name.lower()
    if "bond" in name_lower or "obbligaz" in name_lower or "fixed income" in name_lower:
        return "bond"
    return "equity"


def _is_tech_like(name: str, symbol: str) -> bool:
    tech_keywords = {"tech", "nasdaq", "tecnolog", "semiconductor", "software", "information tech"}
    return any(kw in name for kw in tech_keywords) or "qqq" in symbol


def _is_commodity_like(name: str, symbol: str) -> bool:
    commodity_keywords = {"commodity", "gold", "silver", "oil", "materie prime", "raw material", "metal"}
    return any(kw in name for kw in commodity_keywords)


def run_stress_test(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str | None = None,
) -> StressTestResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    holdings = _load_holdings(repo, portfolio_id, user_id)
    if not holdings:
        return StressTestResponse(
            portfolio_id=portfolio_id,
            scenarios=[],
            portfolio_volatility_pct=None,
            analysis_date=str(date.today()),
        )

    # Compute portfolio volatility
    mu_annual, sigma_annual = _compute_portfolio_return_params(repo, holdings)
    volatility_pct = round(sigma_annual * 100, 2) if sigma_annual > 0 else None

    scenarios: list[StressTestScenarioResult] = []

    # Historical scenarios
    for scenario in HISTORICAL_SCENARIOS:
        try:
            result = _compute_historical_scenario(repo, holdings, scenario)
            scenarios.append(result)
        except Exception:
            logger.warning("Failed to compute historical scenario %s", scenario["id"], exc_info=True)

    # Shock scenarios
    for scenario in SHOCK_SCENARIOS:
        try:
            result = _compute_shock_scenario(holdings, scenario)
            scenarios.append(result)
        except Exception:
            logger.warning("Failed to compute shock scenario %s", scenario["id"], exc_info=True)

    return StressTestResponse(
        portfolio_id=portfolio_id,
        scenarios=scenarios,
        portfolio_volatility_pct=volatility_pct,
        analysis_date=str(date.today()),
    )
