import logging
import math
import random
from datetime import date

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    AggregateDecumulationPlanResponse,
    DecumulationPlanResponse,
    DecumulationYearProjection,
    MonteCarloProjectionResponse,
    MonteCarloYearProjection,
)
from ._holdings import (
    AnalyzedHolding,
    _load_holdings,
    _load_aggregate_holdings,
    _normalize_portfolio_ids,
    _compute_portfolio_return_params,
    _percentile,
)

logger = logging.getLogger(__name__)

NUM_SIMULATIONS = 5_000
MAX_PROJECTION_YEARS = 20
PROJECTION_HORIZONS = [5, 10, 20]


def run_monte_carlo_projection(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str | None = None,
) -> MonteCarloProjectionResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    holdings = _load_holdings(repo, portfolio_id, user_id)
    if not holdings:
        return _empty_monte_carlo_response(portfolio_id)

    mu_annual, sigma_annual = _compute_portfolio_return_params(repo, holdings)
    if sigma_annual == 0.0:
        return _empty_monte_carlo_response(portfolio_id)

    projections = _simulate_paths(mu_annual, sigma_annual)

    return MonteCarloProjectionResponse(
        portfolio_id=portfolio_id,
        num_simulations=NUM_SIMULATIONS,
        horizons=PROJECTION_HORIZONS,
        projections=projections,
        annualized_mean_return_pct=round(mu_annual * 100, 2),
        annualized_volatility_pct=round(sigma_annual * 100, 2),
    )


def run_decumulation_plan(
    repo: PortfolioRepository,
    portfolio_id: int,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float = 0.0,
    current_age: int | None = None,
    user_id: str | None = None,
) -> DecumulationPlanResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    summary = repo.get_summary(portfolio_id, user_id)
    initial_capital = max(0.0, float(summary.market_value) + float(summary.cash_balance))
    holdings = _load_holdings(repo, portfolio_id, user_id)

    mu_annual, sigma_annual = _compute_portfolio_return_params(repo, holdings) if holdings else (0.0, 0.0)
    sustainable_withdrawal = _solve_sustainable_withdrawal(
        initial_capital=initial_capital,
        years=years,
        annual_return_pct=mu_annual * 100,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
    )

    if initial_capital <= 0:
        return _empty_decumulation_response(
            portfolio_id=portfolio_id,
            annual_withdrawal=annual_withdrawal,
            years=years,
            inflation_rate_pct=inflation_rate_pct,
            other_income_annual=other_income_annual,
            current_age=current_age,
        )

    paths = _simulate_decumulation_paths(
        initial_capital=initial_capital,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        mu_annual=mu_annual,
        sigma_annual=sigma_annual,
    )
    final_values = sorted(path["ending_capitals"][-1] for path in paths)
    success_count = sum(1 for path in paths if path["ending_capitals"][-1] > 0)
    projections = _build_decumulation_projections(
        paths=paths,
        years=years,
        annual_withdrawal=annual_withdrawal,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        current_age=current_age,
    )
    depletion_year_p50 = next((projection.year for projection in projections if projection.p50_ending_capital <= 0), None)

    return DecumulationPlanResponse(
        portfolio_id=portfolio_id,
        initial_capital=round(initial_capital, 2),
        annual_withdrawal=round(max(0.0, annual_withdrawal), 2),
        annual_other_income=round(max(0.0, other_income_annual), 2),
        inflation_rate_pct=round(max(0.0, inflation_rate_pct), 2),
        horizon_years=years,
        num_simulations=NUM_SIMULATIONS,
        annualized_mean_return_pct=round(mu_annual * 100, 2),
        annualized_volatility_pct=round(sigma_annual * 100, 2),
        sustainable_withdrawal=round(max(0.0, sustainable_withdrawal), 2),
        success_rate_pct=round((success_count / NUM_SIMULATIONS) * 100, 1),
        depletion_probability_pct=round(((NUM_SIMULATIONS - success_count) / NUM_SIMULATIONS) * 100, 1),
        p25_terminal_value=round(_percentile(final_values, 25), 2),
        p50_terminal_value=round(_percentile(final_values, 50), 2),
        p75_terminal_value=round(_percentile(final_values, 75), 2),
        depletion_year_p50=depletion_year_p50,
        projections=projections,
    )


def run_aggregate_decumulation_plan(
    repo: PortfolioRepository,
    portfolio_ids: list[int],
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float = 0.0,
    current_age: int | None = None,
    user_id: str | None = None,
) -> AggregateDecumulationPlanResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    normalized_ids = _normalize_portfolio_ids(portfolio_ids)
    if not normalized_ids:
        raise ValueError("Seleziona almeno un portafoglio")

    portfolios = {portfolio.id: portfolio for portfolio in repo.list_portfolios(user_id)}
    missing_ids = [portfolio_id for portfolio_id in normalized_ids if portfolio_id not in portfolios]
    if missing_ids:
        raise ValueError("Uno o pi\u00f9 portafogli non sono disponibili")

    base_currencies = {portfolios[portfolio_id].base_currency for portfolio_id in normalized_ids}
    if len(base_currencies) != 1:
        raise ValueError("I portafogli aggregati devono avere la stessa valuta base")
    base_currency = next(iter(base_currencies))

    summaries = [repo.get_summary(portfolio_id, user_id) for portfolio_id in normalized_ids]
    initial_capital = sum(max(0.0, float(summary.market_value) + float(summary.cash_balance)) for summary in summaries)
    holdings = _load_aggregate_holdings(repo, normalized_ids, user_id)
    mu_annual, sigma_annual = _compute_portfolio_return_params(repo, holdings) if holdings else (0.0, 0.0)
    sustainable_withdrawal = _solve_sustainable_withdrawal(
        initial_capital=initial_capital,
        years=years,
        annual_return_pct=mu_annual * 100,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
    )

    if initial_capital <= 0:
        return _empty_aggregate_decumulation_response(
            portfolio_ids=normalized_ids,
            base_currency=base_currency,
            annual_withdrawal=annual_withdrawal,
            years=years,
            inflation_rate_pct=inflation_rate_pct,
            other_income_annual=other_income_annual,
            current_age=current_age,
        )

    paths = _simulate_decumulation_paths(
        initial_capital=initial_capital,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        mu_annual=mu_annual,
        sigma_annual=sigma_annual,
    )
    final_values = sorted(path["ending_capitals"][-1] for path in paths)
    success_count = sum(1 for path in paths if path["ending_capitals"][-1] > 0)
    projections = _build_decumulation_projections(
        paths=paths,
        years=years,
        annual_withdrawal=annual_withdrawal,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        current_age=current_age,
    )
    depletion_year_p50 = next((projection.year for projection in projections if projection.p50_ending_capital <= 0), None)

    return AggregateDecumulationPlanResponse(
        portfolio_ids=normalized_ids,
        base_currency=base_currency,
        initial_capital=round(initial_capital, 2),
        annual_withdrawal=round(max(0.0, annual_withdrawal), 2),
        annual_other_income=round(max(0.0, other_income_annual), 2),
        inflation_rate_pct=round(max(0.0, inflation_rate_pct), 2),
        horizon_years=years,
        num_simulations=NUM_SIMULATIONS,
        annualized_mean_return_pct=round(mu_annual * 100, 2),
        annualized_volatility_pct=round(sigma_annual * 100, 2),
        sustainable_withdrawal=round(max(0.0, sustainable_withdrawal), 2),
        success_rate_pct=round((success_count / NUM_SIMULATIONS) * 100, 1),
        depletion_probability_pct=round(((NUM_SIMULATIONS - success_count) / NUM_SIMULATIONS) * 100, 1),
        p25_terminal_value=round(_percentile(final_values, 25), 2),
        p50_terminal_value=round(_percentile(final_values, 50), 2),
        p75_terminal_value=round(_percentile(final_values, 75), 2),
        depletion_year_p50=depletion_year_p50,
        projections=projections,
    )


def _simulate_paths(
    mu_annual: float,
    sigma_annual: float,
) -> list[MonteCarloYearProjection]:
    drift = mu_annual - 0.5 * sigma_annual**2
    rng = random.Random(42)

    # Each simulation: cumulative log-return at each year
    all_paths: list[list[float]] = []
    for _ in range(NUM_SIMULATIONS):
        cum = 0.0
        path = [100.0]
        for _ in range(MAX_PROJECTION_YEARS):
            shock = rng.gauss(0, 1)
            cum += drift + sigma_annual * shock
            path.append(100.0 * math.exp(cum))
        all_paths.append(path)

    projections: list[MonteCarloYearProjection] = []
    for year_idx in range(MAX_PROJECTION_YEARS + 1):
        values = sorted(p[year_idx] for p in all_paths)
        projections.append(
            MonteCarloYearProjection(
                year=year_idx,
                p10=round(_percentile(values, 10), 1),
                p25=round(_percentile(values, 25), 1),
                p50=round(_percentile(values, 50), 1),
                p75=round(_percentile(values, 75), 1),
                p90=round(_percentile(values, 90), 1),
            )
        )
    return projections


def _simulate_decumulation_paths(
    *,
    initial_capital: float,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    mu_annual: float,
    sigma_annual: float,
) -> list[dict[str, list[float]]]:
    drift = mu_annual - 0.5 * sigma_annual**2
    inflation = max(0.0, inflation_rate_pct) / 100.0
    rng = random.Random(42)
    paths: list[dict[str, list[float]]] = []

    for _ in range(NUM_SIMULATIONS):
        capital = initial_capital
        withdrawal = max(0.0, annual_withdrawal)
        ending_capitals: list[float] = []
        effective_rates: list[float] = []
        depleted_flags: list[float] = []

        for _year in range(years):
            starting_capital = capital
            annual_return = math.exp(drift + sigma_annual * rng.gauss(0, 1)) - 1 if sigma_annual > 0 else mu_annual
            capital = max(0.0, capital * (1 + annual_return))
            net_withdrawal = max(0.0, withdrawal - max(0.0, other_income_annual))
            effective_rates.append((net_withdrawal / starting_capital) * 100 if starting_capital > 0 else 0.0)
            capital = max(0.0, capital - net_withdrawal)
            ending_capitals.append(capital)
            depleted_flags.append(1.0 if capital <= 0 else 0.0)
            withdrawal *= (1 + inflation)

        paths.append(
            {
                "ending_capitals": ending_capitals,
                "effective_rates": effective_rates,
                "depleted_flags": depleted_flags,
            }
        )

    return paths


def _build_decumulation_projections(
    *,
    paths: list[dict[str, list[float]]],
    years: int,
    annual_withdrawal: float,
    inflation_rate_pct: float,
    other_income_annual: float,
    current_age: int | None,
) -> list[DecumulationYearProjection]:
    inflation = max(0.0, inflation_rate_pct) / 100.0
    gross_withdrawal = max(0.0, annual_withdrawal)
    projections: list[DecumulationYearProjection] = []

    for year_index in range(years):
        capitals = sorted(path["ending_capitals"][year_index] for path in paths)
        rates = sorted(path["effective_rates"][year_index] for path in paths)
        depleted_count = sum(path["depleted_flags"][year_index] for path in paths)
        net_withdrawal = max(0.0, gross_withdrawal - max(0.0, other_income_annual))

        projections.append(
            DecumulationYearProjection(
                year=year_index + 1,
                age=(current_age + year_index + 1) if current_age else None,
                gross_withdrawal=round(gross_withdrawal, 2),
                net_withdrawal=round(net_withdrawal, 2),
                p25_ending_capital=round(_percentile(capitals, 25), 2),
                p50_ending_capital=round(_percentile(capitals, 50), 2),
                p75_ending_capital=round(_percentile(capitals, 75), 2),
                p50_effective_withdrawal_rate_pct=round(_percentile(rates, 50), 2),
                depletion_probability_pct=round((depleted_count / NUM_SIMULATIONS) * 100, 1),
            )
        )
        gross_withdrawal *= (1 + inflation)

    return projections


def _solve_sustainable_withdrawal(
    *,
    initial_capital: float,
    years: int,
    annual_return_pct: float,
    inflation_rate_pct: float,
    other_income_annual: float,
) -> float:
    if initial_capital <= 0 or years <= 0:
        return 0.0

    nominal = annual_return_pct / 100.0
    inflation = inflation_rate_pct / 100.0
    real_rate = ((1 + nominal) / (1 + inflation)) - 1

    if abs(real_rate) < 1e-9:
        return max(0.0, initial_capital / years + other_income_annual)

    denominator = 1 - (1 + real_rate) ** (-years)
    if denominator <= 0:
        return max(0.0, other_income_annual)
    return max(0.0, initial_capital * real_rate / denominator + other_income_annual)


def _empty_monte_carlo_response(portfolio_id: int) -> MonteCarloProjectionResponse:
    return MonteCarloProjectionResponse(
        portfolio_id=portfolio_id,
        num_simulations=0,
        horizons=PROJECTION_HORIZONS,
        projections=[],
        annualized_mean_return_pct=0.0,
        annualized_volatility_pct=0.0,
    )


def _empty_decumulation_response(
    *,
    portfolio_id: int,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    current_age: int | None,
) -> DecumulationPlanResponse:
    projections = [
        DecumulationYearProjection(
            year=year,
            age=(current_age + year) if current_age else None,
            gross_withdrawal=round(max(0.0, annual_withdrawal) * ((1 + max(0.0, inflation_rate_pct) / 100.0) ** (year - 1)), 2),
            net_withdrawal=round(max(0.0, max(0.0, annual_withdrawal) - max(0.0, other_income_annual)), 2),
            p25_ending_capital=0.0,
            p50_ending_capital=0.0,
            p75_ending_capital=0.0,
            p50_effective_withdrawal_rate_pct=0.0,
            depletion_probability_pct=100.0,
        )
        for year in range(1, years + 1)
    ]
    return DecumulationPlanResponse(
        portfolio_id=portfolio_id,
        initial_capital=0.0,
        annual_withdrawal=round(max(0.0, annual_withdrawal), 2),
        annual_other_income=round(max(0.0, other_income_annual), 2),
        inflation_rate_pct=round(max(0.0, inflation_rate_pct), 2),
        horizon_years=years,
        num_simulations=0,
        annualized_mean_return_pct=0.0,
        annualized_volatility_pct=0.0,
        sustainable_withdrawal=0.0,
        success_rate_pct=0.0,
        depletion_probability_pct=100.0,
        p25_terminal_value=0.0,
        p50_terminal_value=0.0,
        p75_terminal_value=0.0,
        depletion_year_p50=1 if years > 0 else None,
        projections=projections,
    )


def _empty_aggregate_decumulation_response(
    *,
    portfolio_ids: list[int],
    base_currency: str,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    current_age: int | None,
) -> AggregateDecumulationPlanResponse:
    projections = [
        DecumulationYearProjection(
            year=year,
            age=(current_age + year) if current_age else None,
            gross_withdrawal=round(max(0.0, annual_withdrawal) * ((1 + max(0.0, inflation_rate_pct) / 100.0) ** (year - 1)), 2),
            net_withdrawal=round(max(0.0, max(0.0, annual_withdrawal) - max(0.0, other_income_annual)), 2),
            p25_ending_capital=0.0,
            p50_ending_capital=0.0,
            p75_ending_capital=0.0,
            p50_effective_withdrawal_rate_pct=0.0,
            depletion_probability_pct=100.0,
        )
        for year in range(1, years + 1)
    ]
    return AggregateDecumulationPlanResponse(
        portfolio_ids=portfolio_ids,
        base_currency=base_currency,
        initial_capital=0.0,
        annual_withdrawal=round(max(0.0, annual_withdrawal), 2),
        annual_other_income=round(max(0.0, other_income_annual), 2),
        inflation_rate_pct=round(max(0.0, inflation_rate_pct), 2),
        horizon_years=years,
        num_simulations=0,
        annualized_mean_return_pct=0.0,
        annualized_volatility_pct=0.0,
        sustainable_withdrawal=0.0,
        success_rate_pct=0.0,
        depletion_probability_pct=100.0,
        p25_terminal_value=0.0,
        p50_terminal_value=0.0,
        p75_terminal_value=0.0,
        depletion_year_p50=1 if years > 0 else None,
        projections=projections,
    )
