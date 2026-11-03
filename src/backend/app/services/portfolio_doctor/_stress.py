import logging
import math
from collections import defaultdict
from datetime import date

from sqlalchemy import text

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    StressTestAssetImpact,
    StressTestClassImpact,
    StressTestResponse,
    StressTestScenarioResult,
    VolatilityInfo,
)
from ...constants.stress_scenarios import (
    HISTORICAL_CLASS_PROXIES,
    HISTORICAL_MIN_COVERAGE_PCT,
    HISTORICAL_SCENARIOS,
    SHOCK_SCENARIOS,
)
from ._holdings import (
    AnalyzedHolding,
    PortfolioRef,
    _historical_return_stats,
    _load_holdings,
    _long_term_return_assumptions,
    holding_asset_class,
    resolve_doctor_scope,
)

logger = logging.getLogger(__name__)


HISTORICAL_PROXY_METHODOLOGY_NOTE = (
    "Stima basata su indici di riferimento in dollari (USD) per asset class: "
    "non include l'effetto del cambio EUR/USD, che può cambiare in modo "
    "rilevante il risultato per un investitore in euro."
)


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
    """Portfolio impact during a historical scenario (TASK-38, V365-001).

    - coverage_pct: weight of holdings with at least 2 price bars in the
      window (cash included: its return is 0), over the total weight.
    - coverage >= HISTORICAL_MIN_COVERAGE_PCT -> method "historical": real
      window returns for the covered part, class proxies for the rest
      (flag "uncovered_weight_filled_with_class_proxy").
    - below it -> method "proxy": sum(weight_i x class proxy_i) for every
      holding (flag "class_proxy_drawdowns").
    - empty portfolio -> method "not_available".
    The result never depends on the scenario benchmark alone.
    """
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

    total_weight = sum(max(0.0, h.weight_pct) for h in holdings) / 100.0
    if total_weight <= 0:
        return _not_available_scenario(scenario)

    # Real return over the window for every holding that has it. Cash is
    # covered by definition: its return in the portfolio currency is 0.
    real_returns: dict[int, float] = {}
    for holding in holdings:
        if holding.asset_type == "cash":
            real_returns[holding.asset_id] = 0.0
            continue
        series = prices_by_asset.get(holding.asset_id, [])
        if len(series) < 2:
            continue
        first_price = series[0][1]
        last_price = series[-1][1]
        real_returns[holding.asset_id] = (last_price - first_price) / first_price

    covered_weight = sum(
        max(0.0, h.weight_pct) / 100.0 for h in holdings if h.asset_id in real_returns
    )
    coverage_pct = round(covered_weight / total_weight * 100.0, 2)
    method = "historical" if coverage_pct >= HISTORICAL_MIN_COVERAGE_PCT else "proxy"

    proxies = HISTORICAL_CLASS_PROXIES[scenario["id"]]
    flags: list[str] = ["class_proxy_drawdowns"] if method == "proxy" else []
    weighted_return = 0.0
    proxy_return = 0.0
    asset_impacts: list[StressTestAssetImpact] = []
    # (class, source) -> [weight_pct, contribution as fraction x weight fraction]
    rows: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])

    for holding in holdings:
        weight_fraction = max(0.0, holding.weight_pct) / 100.0
        asset_class = holding_asset_class(holding)
        if method == "historical" and holding.asset_id in real_returns:
            asset_return = real_returns[holding.asset_id]
            source = "historical"
        else:
            asset_return = _class_proxy(proxies, asset_class, flags) / 100.0
            source = "proxy"
            proxy_return += asset_return * weight_fraction
            if method == "historical" and "uncovered_weight_filled_with_class_proxy" not in flags:
                flags.append("uncovered_weight_filled_with_class_proxy")
        weighted_return += asset_return * weight_fraction
        row = rows[(asset_class, source)]
        row[0] += max(0.0, holding.weight_pct)
        row[1] += asset_return * weight_fraction
        if holding.asset_type != "cash":
            asset_impacts.append(
                StressTestAssetImpact(
                    symbol=holding.symbol,
                    name=holding.name,
                    weight_pct=round(holding.weight_pct, 2),
                    estimated_loss_pct=round(asset_return * 100, 2),
                    asset_class=asset_class,
                )
            )

    # Normalized on the total weight, so contributions add up to the impact.
    portfolio_impact = weighted_return / total_weight * 100.0
    class_breakdown = [
        StressTestClassImpact(
            asset_class=cls,
            weight_pct=round(weight_pct, 2),
            drawdown_pct=round(contribution / (weight_pct / 100.0) * 100.0, 2) if weight_pct > 0 else 0.0,
            source=source,
            contribution_pct=round(contribution / total_weight * 100.0, 2),
        )
        for (cls, source), (weight_pct, contribution) in sorted(
            rows.items(), key=lambda item: (item[1][1], item[0])
        )
    ]

    if method == "historical":
        # Path drawdown of the part with real prices (uncovered weight held
        # flat), plus the proxy contribution of the uncovered part. Proxies
        # are window returns, so their own path is unknown: approximation.
        covered_prices = {aid: prices_by_asset[aid] for aid in real_returns if aid in prices_by_asset}
        max_dd = _compute_weighted_drawdown(covered_prices, holdings)
        max_dd = min(max_dd + proxy_return / total_weight * 100.0, portfolio_impact, 0.0)
    else:
        # The proxy windows run roughly peak -> trough.
        max_dd = min(portfolio_impact, 0.0)

    # Estimate recovery months (rough heuristic based on drawdown depth)
    recovery_months = None
    if max_dd < 0:
        recovery_months = max(1, int(abs(max_dd) / 2.5))

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
        most_impacted_assets=_rank_most_impacted(asset_impacts),
        method=method,
        coverage_pct=coverage_pct,
        methodology_note=(
            HISTORICAL_PROXY_METHODOLOGY_NOTE
            if any(row.source == "proxy" for row in class_breakdown)
            else None
        ),
        class_breakdown=class_breakdown,
        flags=flags,
    )


CRYPTO_PRE_INCEPTION_FLAG = "crypto_pre_inception_equity_proxy"
UNKNOWN_CLASS_PROXY_FLAG = "unknown_asset_class_equity_proxy"


def _class_proxy(proxies: dict[str, float | None], asset_class: str, flags: list[str]) -> float:
    """Drawdown proxy (percent) of a class in a historical scenario.

    ``unknown`` and crypto before it existed take the equity proxy
    (prudential choice) and raise a flag.
    """
    value = proxies.get(asset_class)
    if value is not None:
        return value
    flag = CRYPTO_PRE_INCEPTION_FLAG if asset_class == "crypto" else UNKNOWN_CLASS_PROXY_FLAG
    if flag not in flags:
        flags.append(flag)
    return proxies["equity"]


def _not_available_scenario(scenario: dict) -> StressTestScenarioResult:
    """Empty portfolio: nothing to stress."""
    return StressTestScenarioResult(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        scenario_type="historical",
        period=scenario["period"],
        estimated_portfolio_impact_pct=0.0,
        max_drawdown_pct=None,
        recovery_months=None,
        benchmark_drawdown_pct=scenario["benchmark_drawdown"],
        risk_level="low",
        method="not_available",
        coverage_pct=None,
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


def _rank_most_impacted(asset_impacts: list[StressTestAssetImpact], limit: int = 5) -> list[StressTestAssetImpact]:
    """Only real losses, worst first; ties by larger weight, then symbol."""
    losses = [a for a in asset_impacts if a.estimated_loss_pct < 0]
    losses.sort(key=lambda a: (a.estimated_loss_pct, -a.weight_pct, a.symbol))
    return losses[:limit]


UNKNOWN_CLASS_FLAG = "unknown_asset_class_equity_shock"


def _compute_shock_scenario(
    holdings: list[AnalyzedHolding],
    scenario: dict,
) -> StressTestScenarioResult:
    """Apply synthetic shocks to asset classes and compute portfolio impact.

    Every class of the shared classifier has its own shock in the scenario
    table. ``unknown`` instruments get the equity shock as a prudential choice,
    are still reported as ``unknown`` and raise ``UNKNOWN_CLASS_FLAG``.
    """
    shocks = scenario["shocks"]
    tech_mult = scenario.get("tech_multiplier", 1.0)

    weighted_impact = 0.0
    covered_weight = 0.0
    asset_impacts: list[StressTestAssetImpact] = []
    flags: list[str] = []
    class_weight: dict[str, float] = defaultdict(float)
    class_shock: dict[str, float] = {}
    class_contribution: dict[str, float] = defaultdict(float)

    for holding in holdings:
        asset_class = _shock_asset_class(holding)
        if asset_class in shocks:
            base_shock = shocks[asset_class]
        else:
            base_shock = shocks["equity"]
            if UNKNOWN_CLASS_FLAG not in flags:
                flags.append(UNKNOWN_CLASS_FLAG)

        # The tech multiplier only concerns equity holdings.
        multiplier = 1.0
        if tech_mult != 1.0 and asset_class == "equity" and _is_tech_like(
            holding.name.lower(), holding.symbol.lower()
        ):
            multiplier = tech_mult

        asset_shock = base_shock * multiplier
        weight_fraction = holding.weight_pct / 100.0
        weighted_impact += asset_shock * weight_fraction
        covered_weight += weight_fraction
        class_weight[asset_class] += holding.weight_pct
        class_shock[asset_class] = base_shock
        class_contribution[asset_class] += asset_shock * weight_fraction

        asset_impacts.append(
            StressTestAssetImpact(
                symbol=holding.symbol,
                name=holding.name,
                weight_pct=round(holding.weight_pct, 2),
                estimated_loss_pct=round(asset_shock * 100, 2),
                asset_class=asset_class,
            )
        )

    portfolio_impact = (weighted_impact / covered_weight * 100.0) if covered_weight > 0 else 0.0

    # Contributions are normalized like the portfolio impact, so they add up to it.
    class_breakdown = [
        StressTestClassImpact(
            asset_class=cls,
            weight_pct=round(class_weight[cls], 2),
            shock_pct=round(class_shock[cls] * 100, 2),
            contribution_pct=round(
                class_contribution[cls] / covered_weight * 100.0 if covered_weight > 0 else 0.0, 2
            ),
        )
        for cls in sorted(class_weight, key=lambda c: (class_contribution[c], c))
    ]
    affected_classes = [row.asset_class for row in class_breakdown if row.contribution_pct != 0 or row.shock_pct != 0]

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
        most_impacted_assets=_rank_most_impacted(asset_impacts),
        affected_classes=affected_classes,
        class_breakdown=class_breakdown,
        flags=flags,
    )


def _shock_asset_class(holding: AnalyzedHolding) -> str:
    """Asset class of a holding for shock scenarios (shared classifier)."""
    return holding_asset_class(holding)


def _is_tech_like(name: str, symbol: str) -> bool:
    tech_keywords = {"tech", "nasdaq", "tecnolog", "semiconductor", "software", "information tech"}
    return any(kw in name for kw in tech_keywords) or "qqq" in symbol


STRESS_VOLATILITY_METHOD = (
    "realized_portfolio_series_floored_at_long_term_class_mix_volatility"
)


def stress_volatility_info(
    repo: PortfolioRepository,
    holdings: list[AnalyzedHolding],
) -> tuple[float, VolatilityInfo]:
    """Volatility shown with the stress test, with its methodology (TASK-40).

    Same sigma as the Monte Carlo projections: annualized volatility of the
    weighted portfolio series over the last year (correlations included),
    never below the long-term volatility of the class mix (16% for equity,
    6% bond, 15% commodity/gold, 0% cash, with long-term correlations), so a
    calm year does not understate risk. Returns (sigma as a fraction,
    metadata); sigma is 0 and value_pct None without enough history.
    """
    _mu_lt, sigma_long_term = _long_term_return_assumptions(holdings)
    floor_pct = round(sigma_long_term * 100, 2)
    historical = _historical_return_stats(repo, holdings)
    sigma_hist = historical[1] if historical is not None else None
    sigma = max(sigma_hist, sigma_long_term) if sigma_hist is not None else 0.0
    return sigma, VolatilityInfo(
        name="stress_portfolio_volatility",
        value_pct=round(sigma * 100, 2) if sigma > 0 else None,
        method=STRESS_VOLATILITY_METHOD,
        period="last 1y of daily closes (min 20 returns), annualized x sqrt(252)",
        is_floored=sigma_hist is not None and sigma_long_term > sigma_hist,
        floor_pct=floor_pct,
        unfloored_pct=round(sigma_hist * 100, 2) if sigma_hist is not None else None,
    )


def run_stress_test(
    repo: PortfolioRepository,
    portfolio_id: PortfolioRef,
    user_id: str | None = None,
) -> StressTestResponse:
    """Stress test of one portfolio (int) or of several read as one (list)."""
    if not user_id:
        raise ValueError("Utente non valido")

    scope_ref, identity = resolve_doctor_scope(repo, portfolio_id, user_id)
    holdings = _load_holdings(repo, scope_ref, user_id)
    if not holdings:
        return StressTestResponse(
            **identity,
            scenarios=[],
            portfolio_volatility_pct=None,
            analysis_date=str(date.today()),
        )

    _sigma_annual, volatility = stress_volatility_info(repo, holdings)

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
        **identity,
        scenarios=scenarios,
        portfolio_volatility_pct=volatility.value_pct,
        volatility=volatility,
        analysis_date=str(date.today()),
    )
