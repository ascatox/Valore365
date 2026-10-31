import logging
import math
import random
from dataclasses import dataclass, field, replace

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    AggregateDecumulationPlanResponse,
    DecumulationPlanResponse,
    DecumulationYearProjection,
    MonteCarloProjectionResponse,
    MonteCarloYearProjection,
)
from ._holdings import (
    PortfolioRef,
    _compute_portfolio_return_params,
    _load_aggregate_holdings,
    _load_holdings,
    _percentile,
    resolve_doctor_scope,
)

logger = logging.getLogger(__name__)

NUM_SIMULATIONS = 5_000
MAX_PROJECTION_YEARS = 20
PROJECTION_HORIZONS = [5, 10, 20]


def run_monte_carlo_projection(
    repo: PortfolioRepository,
    portfolio_id: PortfolioRef,
    user_id: str | None = None,
) -> MonteCarloProjectionResponse:
    """Monte Carlo of one portfolio (int) or of several read as one (list)."""
    if not user_id:
        raise ValueError("Utente non valido")

    scope_ref, identity = resolve_doctor_scope(repo, portfolio_id, user_id)
    holdings = _load_holdings(repo, scope_ref, user_id)
    if not holdings:
        return _empty_monte_carlo_response(**identity)

    mu_annual, sigma_annual, df_t = _compute_portfolio_return_params(repo, holdings)
    if sigma_annual == 0.0:
        return _empty_monte_carlo_response(**identity)

    projections = _simulate_paths(mu_annual, sigma_annual, df_t)

    return MonteCarloProjectionResponse(
        **identity,
        num_simulations=NUM_SIMULATIONS,
        horizons=PROJECTION_HORIZONS,
        projections=projections,
        annualized_mean_return_pct=round(mu_annual * 100, 2),
        annualized_volatility_pct=round(sigma_annual * 100, 2),
    )


@dataclass(frozen=True)
class DecumulationSchedule:
    """Optional cash-flow events of a decumulation plan, all in today's money.

    Years are 1-based: year 1 is the year starting at ``current_age``.
    """

    capital_floor: float = 0.0
    pension_annual: float = 0.0
    pension_start_year: int | None = None
    one_off_by_year: dict[int, float] = field(default_factory=dict)
    # Desired range of the capital left at the end of the horizon; 0 = unset.
    terminal_target_min: float = 0.0
    terminal_target_max: float = 0.0

    @property
    def required_terminal_capital(self) -> float:
        return max(self.capital_floor, self.terminal_target_min)


def _build_decumulation_schedule(
    *,
    years: int,
    current_age: int | None,
    capital_floor: float,
    pension_annual: float,
    pension_start_age: int | None,
    one_off_expenses: list[tuple[int, float]] | None,
    terminal_target_min: float = 0.0,
    terminal_target_max: float = 0.0,
) -> DecumulationSchedule:
    pension = max(0.0, pension_annual)
    pension_start_year: int | None = None
    if pension > 0:
        if pension_start_age is None:
            pension_start_year = 1
        elif current_age is not None:
            candidate_year = max(1, pension_start_age - current_age + 1)
            pension_start_year = candidate_year if candidate_year <= years else None

    one_off_by_year: dict[int, float] = {}
    if current_age is not None:
        for age, amount in one_off_expenses or []:
            year = age - current_age + 1
            if 1 <= year <= years and amount > 0:
                one_off_by_year[year] = one_off_by_year.get(year, 0.0) + amount

    return DecumulationSchedule(
        capital_floor=max(0.0, capital_floor),
        pension_annual=pension if pension_start_year is not None else 0.0,
        pension_start_year=pension_start_year,
        one_off_by_year=one_off_by_year,
        terminal_target_min=max(0.0, terminal_target_min),
        terminal_target_max=max(0.0, terminal_target_max),
    )


def run_decumulation_plan(
    repo: PortfolioRepository,
    portfolio_id: int,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float = 0.0,
    capital_gains_tax_rate_pct: float = 26.0,
    current_age: int | None = None,
    user_id: str | None = None,
    capital_floor: float = 0.0,
    pension_annual: float = 0.0,
    pension_start_age: int | None = None,
    one_off_expenses: list[tuple[int, float]] | None = None,
    terminal_target_min: float = 0.0,
    terminal_target_max: float = 0.0,
) -> DecumulationPlanResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    summary = repo.get_summary(portfolio_id, user_id)
    initial_capital = max(0.0, float(summary.market_value) + float(summary.cash_balance))
    initial_cost_basis = max(0.0, float(summary.cost_basis) + float(summary.cash_balance))
    holdings = _load_holdings(repo, portfolio_id, user_id)

    fields = _compute_decumulation_fields(
        repo=repo,
        holdings=holdings,
        initial_capital=initial_capital,
        initial_cost_basis=initial_cost_basis,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        capital_gains_tax_rate_pct=capital_gains_tax_rate_pct,
        current_age=current_age,
        schedule=_build_decumulation_schedule(
            years=years,
            current_age=current_age,
            capital_floor=capital_floor,
            pension_annual=pension_annual,
            pension_start_age=pension_start_age,
            one_off_expenses=one_off_expenses,
            terminal_target_min=terminal_target_min,
            terminal_target_max=terminal_target_max,
        ),
    )
    return DecumulationPlanResponse(portfolio_id=portfolio_id, **fields)


def run_aggregate_decumulation_plan(
    repo: PortfolioRepository,
    portfolio_ids: list[int],
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float = 0.0,
    capital_gains_tax_rate_pct: float = 26.0,
    current_age: int | None = None,
    user_id: str | None = None,
    capital_floor: float = 0.0,
    pension_annual: float = 0.0,
    pension_start_age: int | None = None,
    one_off_expenses: list[tuple[int, float]] | None = None,
    terminal_target_min: float = 0.0,
    terminal_target_max: float = 0.0,
) -> AggregateDecumulationPlanResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    # Shared scope validation: empty selection or mixed base currencies -> 400,
    # a portfolio the user does not own -> 404 ("Portfolio non trovato").
    scope = repo.resolve_portfolio_scope(portfolio_ids, user_id)
    normalized_ids = list(scope.portfolio_ids)
    base_currency = scope.base_currency

    summaries = [repo.get_summary(portfolio_id, user_id) for portfolio_id in normalized_ids]
    initial_capital = sum(max(0.0, float(summary.market_value) + float(summary.cash_balance)) for summary in summaries)
    initial_cost_basis = sum(max(0.0, float(summary.cost_basis) + float(summary.cash_balance)) for summary in summaries)
    holdings = _load_aggregate_holdings(repo, normalized_ids, user_id)

    fields = _compute_decumulation_fields(
        repo=repo,
        holdings=holdings,
        initial_capital=initial_capital,
        initial_cost_basis=initial_cost_basis,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        capital_gains_tax_rate_pct=capital_gains_tax_rate_pct,
        current_age=current_age,
        schedule=_build_decumulation_schedule(
            years=years,
            current_age=current_age,
            capital_floor=capital_floor,
            pension_annual=pension_annual,
            pension_start_age=pension_start_age,
            one_off_expenses=one_off_expenses,
            terminal_target_min=terminal_target_min,
            terminal_target_max=terminal_target_max,
        ),
    )
    return AggregateDecumulationPlanResponse(portfolio_ids=normalized_ids, base_currency=base_currency, **fields)


def _compute_decumulation_fields(
    *,
    repo: PortfolioRepository,
    holdings: list,
    initial_capital: float,
    initial_cost_basis: float,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    capital_gains_tax_rate_pct: float,
    current_age: int | None,
    schedule: DecumulationSchedule,
) -> dict:
    """Shared body of the single and aggregate decumulation responses."""
    estimated_embedded_gain_ratio_pct = _estimate_embedded_gain_ratio(initial_capital, initial_cost_basis) * 100
    mu_annual, sigma_annual, df_t = _compute_portfolio_return_params(repo, holdings) if holdings else (0.0, 0.0, 30.0)
    solve_kwargs = {
        "initial_capital": initial_capital,
        "years": years,
        "annual_return_pct": mu_annual * 100,
        "inflation_rate_pct": inflation_rate_pct,
        "other_income_annual": other_income_annual,
        "capital_gains_tax_rate_pct": capital_gains_tax_rate_pct,
        "embedded_gain_ratio_pct": estimated_embedded_gain_ratio_pct,
    }
    sustainable_withdrawal = _solve_sustainable_withdrawal(**solve_kwargs, schedule=schedule)
    # Spending that leaves the top of the terminal range instead of the bottom.
    withdrawal_for_terminal_max = (
        _solve_sustainable_withdrawal(**solve_kwargs, schedule=replace(schedule, terminal_target_min=schedule.terminal_target_max))
        if schedule.terminal_target_max > 0
        else None
    )
    common = {
        "annual_withdrawal": round(max(0.0, annual_withdrawal), 2),
        "annual_other_income": round(max(0.0, other_income_annual), 2),
        "inflation_rate_pct": round(max(0.0, inflation_rate_pct), 2),
        "capital_gains_tax_rate_pct": round(max(0.0, capital_gains_tax_rate_pct), 2),
        "estimated_embedded_gain_ratio_pct": round(max(0.0, estimated_embedded_gain_ratio_pct), 2),
        "horizon_years": years,
        "capital_floor": round(schedule.capital_floor, 2),
        "pension_annual": round(schedule.pension_annual, 2),
        "pension_start_year": schedule.pension_start_year,
        "terminal_target_min": round(schedule.terminal_target_min, 2),
        "terminal_target_max": round(schedule.terminal_target_max, 2),
        "withdrawal_for_terminal_max": round(max(0.0, withdrawal_for_terminal_max), 2) if withdrawal_for_terminal_max is not None else None,
    }

    if initial_capital <= 0:
        return {
            **common,
            **_empty_decumulation_fields(
                annual_withdrawal=annual_withdrawal,
                years=years,
                inflation_rate_pct=inflation_rate_pct,
                other_income_annual=other_income_annual,
                current_age=current_age,
                schedule=schedule,
            ),
        }

    paths = _simulate_decumulation_paths(
        initial_capital=initial_capital,
        initial_cost_basis=initial_cost_basis,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        capital_gains_tax_rate_pct=capital_gains_tax_rate_pct,
        mu_annual=mu_annual,
        sigma_annual=sigma_annual,
        df_t=df_t,
        schedule=schedule,
    )
    final_values = sorted(path["ending_capitals"][-1] for path in paths)
    success_count = sum(1 for path in paths if not path["floor_breached_flags"][-1])
    depleted_count = sum(1 for path in paths if path["ending_capitals"][-1] <= 0)
    projections = _build_decumulation_projections(
        paths=paths,
        years=years,
        other_income_annual=other_income_annual,
        current_age=current_age,
    )
    depletion_year_p50 = next((projection.year for projection in projections if projection.p50_ending_capital <= 0), None)
    terminal_range = _terminal_range_probabilities(final_values, schedule, inflation_rate_pct, years)
    floor_breach_year_p50 = (
        next((p.year for p in projections if p.p50_ending_capital < p.capital_floor), None)
        if schedule.capital_floor > 0
        else depletion_year_p50
    )

    return {
        **common,
        "initial_capital": round(initial_capital, 2),
        "num_simulations": NUM_SIMULATIONS,
        "annualized_mean_return_pct": round(mu_annual * 100, 2),
        "annualized_volatility_pct": round(sigma_annual * 100, 2),
        "sustainable_withdrawal": round(max(0.0, sustainable_withdrawal), 2),
        "success_rate_pct": round((success_count / NUM_SIMULATIONS) * 100, 1),
        "depletion_probability_pct": round((depleted_count / NUM_SIMULATIONS) * 100, 1),
        "floor_breach_probability_pct": round(((NUM_SIMULATIONS - success_count) / NUM_SIMULATIONS) * 100, 1),
        "p25_terminal_value": round(_percentile(final_values, 25), 2),
        "p50_terminal_value": round(_percentile(final_values, 50), 2),
        "p75_terminal_value": round(_percentile(final_values, 75), 2),
        "depletion_year_p50": depletion_year_p50,
        "floor_breach_year_p50": floor_breach_year_p50,
        "p50_terminal_value_real": round(_percentile(final_values, 50) / _inflation_factor(inflation_rate_pct, years), 2),
        **terminal_range,
        "projections": projections,
    }


def _inflation_factor(inflation_rate_pct: float, years: int) -> float:
    return (1 + max(0.0, inflation_rate_pct) / 100.0) ** years


def _terminal_range_probabilities(
    final_values: list[float],
    schedule: DecumulationSchedule,
    inflation_rate_pct: float,
    years: int,
) -> dict:
    """Share of paths ending below, inside and above the terminal target range.

    The range is in today's money, so it is compared with nominal terminal
    values after indexing it to the end of the horizon.
    """
    if schedule.terminal_target_min <= 0 and schedule.terminal_target_max <= 0:
        return {}
    num_paths = len(final_values) or 1
    factor = _inflation_factor(inflation_rate_pct, years)
    low = schedule.terminal_target_min * factor
    high = schedule.terminal_target_max * factor if schedule.terminal_target_max > 0 else math.inf
    below = sum(1 for value in final_values if value < low)
    above = sum(1 for value in final_values if value > high)
    return {
        "terminal_below_range_probability_pct": round((below / num_paths) * 100, 1),
        "terminal_in_range_probability_pct": round(((num_paths - below - above) / num_paths) * 100, 1),
        "terminal_above_range_probability_pct": round((above / num_paths) * 100, 1),
    }


def _t_random(rng: random.Random, df: float) -> float:
    """Generate a Student-t distributed random variate.

    Uses the ratio of a standard normal to the sqrt of a chi-squared/df.
    When df >= 30 the distribution is effectively Gaussian.
    """
    if df >= 30.0:
        return rng.gauss(0, 1)
    # chi-squared(df) = sum of df standard normals squared
    # For efficiency use the gamma distribution: chi2 ~ Gamma(df/2, 2)
    chi2 = rng.gammavariate(df / 2.0, 2.0)
    if chi2 <= 0:
        return rng.gauss(0, 1)
    return rng.gauss(0, 1) / math.sqrt(chi2 / df)


def _simulate_paths(
    mu_annual: float,
    sigma_annual: float,
    df_t: float = 30.0,
) -> list[MonteCarloYearProjection]:
    # mu_annual is a compound rate, so the median path grows at exactly mu_annual.
    drift = math.log1p(mu_annual)
    rng = random.Random(42)

    # Scale factor: the Student-t with df degrees of freedom has variance
    # df/(df-2) for df>2.  We scale the shock so that the overall variance
    # still matches sigma_annual (preserves calibration while adding fat tails).
    t_scale = math.sqrt((df_t - 2.0) / df_t) if df_t > 2.0 else 1.0

    all_paths: list[list[float]] = []
    for _ in range(NUM_SIMULATIONS):
        cum = 0.0
        path = [100.0]
        for _ in range(MAX_PROJECTION_YEARS):
            shock = _t_random(rng, df_t) * t_scale
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


def _schedule_income(schedule: DecumulationSchedule, year: int, inflation_factor: float) -> float:
    if schedule.pension_start_year is None or year < schedule.pension_start_year:
        return 0.0
    return schedule.pension_annual * inflation_factor


def _simulate_decumulation_paths(
    *,
    initial_capital: float,
    initial_cost_basis: float,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    capital_gains_tax_rate_pct: float,
    mu_annual: float,
    sigma_annual: float,
    df_t: float = 30.0,
    schedule: DecumulationSchedule | None = None,
) -> list[dict[str, list[float]]]:
    schedule = schedule or DecumulationSchedule()
    # mu_annual is a compound rate, so the median path grows at exactly mu_annual.
    drift = math.log1p(mu_annual)
    inflation = max(0.0, inflation_rate_pct) / 100.0
    tax_rate = max(0.0, capital_gains_tax_rate_pct) / 100.0
    t_scale = math.sqrt((df_t - 2.0) / df_t) if df_t > 2.0 else 1.0
    base_other_income = max(0.0, other_income_annual)
    rng = random.Random(42)
    paths: list[dict[str, list[float]]] = []

    for _ in range(NUM_SIMULATIONS):
        capital = initial_capital
        cost_basis = max(0.0, initial_cost_basis)
        spending_target = max(0.0, annual_withdrawal)
        floor_breached = False
        ending_capitals: list[float] = []
        effective_rates: list[float] = []
        depleted_flags: list[float] = []
        floor_breached_flags: list[float] = []
        capital_floors: list[float] = []
        target_net_spendings: list[float] = []
        gross_withdrawals: list[float] = []
        estimated_taxes: list[float] = []
        net_withdrawals: list[float] = []
        net_spending_after_tax: list[float] = []
        other_incomes: list[float] = []

        for year_index in range(years):
            year = year_index + 1
            inflation_factor = (1 + inflation) ** year_index
            income = base_other_income + _schedule_income(schedule, year, inflation_factor)
            one_off = schedule.one_off_by_year.get(year, 0.0) * inflation_factor
            year_target = spending_target + one_off

            starting_capital = capital
            annual_return = math.exp(drift + sigma_annual * _t_random(rng, df_t) * t_scale) - 1 if sigma_annual > 0 else mu_annual
            capital = max(0.0, capital * (1 + annual_return))
            capital_before_sale = capital

            net_needed_from_portfolio = max(0.0, year_target - income)
            embedded_gain_ratio = _estimate_embedded_gain_ratio(capital_before_sale, cost_basis)
            gross_sale = _solve_gross_sale_for_net_need(net_needed_from_portfolio, embedded_gain_ratio, tax_rate)
            gross_sale = min(gross_sale, capital_before_sale)
            taxes = gross_sale * embedded_gain_ratio * tax_rate
            net_from_portfolio = max(0.0, gross_sale - taxes)
            total_net_spending = net_from_portfolio + income

            effective_rates.append((gross_sale / starting_capital) * 100 if starting_capital > 0 else 0.0)
            basis_ratio = min(1.0, cost_basis / capital_before_sale) if capital_before_sale > 0 else 0.0
            basis_sold = gross_sale * basis_ratio
            cost_basis = max(0.0, cost_basis - basis_sold)
            capital = max(0.0, capital_before_sale - gross_sale)
            if capital <= 0:
                cost_basis = 0.0

            # The floor is expressed in today's money, so it grows with inflation.
            capital_floor = schedule.capital_floor * (1 + inflation) ** year
            if schedule.capital_floor > 0:
                floor_breached = floor_breached or capital < capital_floor
            else:
                floor_breached = floor_breached or capital <= 0

            target_net_spendings.append(year_target)
            gross_withdrawals.append(gross_sale)
            estimated_taxes.append(taxes)
            net_withdrawals.append(net_from_portfolio)
            net_spending_after_tax.append(total_net_spending)
            other_incomes.append(income)
            ending_capitals.append(capital)
            depleted_flags.append(1.0 if capital <= 0 else 0.0)
            floor_breached_flags.append(1.0 if floor_breached else 0.0)
            capital_floors.append(capital_floor)
            spending_target *= (1 + inflation)

        paths.append(
            {
                "ending_capitals": ending_capitals,
                "effective_rates": effective_rates,
                "depleted_flags": depleted_flags,
                "floor_breached_flags": floor_breached_flags,
                "capital_floors": capital_floors,
                "target_net_spendings": target_net_spendings,
                "gross_withdrawals": gross_withdrawals,
                "estimated_taxes": estimated_taxes,
                "net_withdrawals": net_withdrawals,
                "net_spending_after_tax": net_spending_after_tax,
                "other_incomes": other_incomes,
            }
        )

    return paths


def _build_decumulation_projections(
    *,
    paths: list[dict[str, list[float]]],
    years: int,
    other_income_annual: float,
    current_age: int | None,
) -> list[DecumulationYearProjection]:
    projections: list[DecumulationYearProjection] = []
    num_paths = len(paths) or 1

    for year_index in range(years):
        capitals = sorted(path["ending_capitals"][year_index] for path in paths)
        rates = sorted(path["effective_rates"][year_index] for path in paths)
        depleted_count = sum(path["depleted_flags"][year_index] for path in paths)
        breached_count = sum(path["floor_breached_flags"][year_index] for path in paths)
        target_net_values = sorted(path["target_net_spendings"][year_index] for path in paths)
        gross_values = sorted(path["gross_withdrawals"][year_index] for path in paths)
        tax_values = sorted(path["estimated_taxes"][year_index] for path in paths)
        net_values = sorted(path["net_withdrawals"][year_index] for path in paths)
        total_net_values = sorted(path["net_spending_after_tax"][year_index] for path in paths)
        income_values = sorted(path["other_incomes"][year_index] for path in paths)
        # Floors and incomes are deterministic: every path carries the same value.
        capital_floor = paths[0]["capital_floors"][year_index] if paths else 0.0

        projections.append(
            DecumulationYearProjection(
                year=year_index + 1,
                age=(current_age + year_index + 1) if current_age else None,
                target_net_spending=round(_percentile(target_net_values, 50), 2),
                gross_withdrawal=round(_percentile(gross_values, 50), 2),
                estimated_taxes=round(_percentile(tax_values, 50), 2),
                net_withdrawal=round(_percentile(net_values, 50), 2),
                other_income=round(_percentile(income_values, 50) if income_values else max(0.0, other_income_annual), 2),
                net_spending_after_tax=round(_percentile(total_net_values, 50), 2),
                p25_ending_capital=round(_percentile(capitals, 25), 2),
                p50_ending_capital=round(_percentile(capitals, 50), 2),
                p75_ending_capital=round(_percentile(capitals, 75), 2),
                p50_effective_withdrawal_rate_pct=round(_percentile(rates, 50), 2),
                depletion_probability_pct=round((depleted_count / num_paths) * 100, 1),
                capital_floor=round(capital_floor, 2),
                floor_breach_probability_pct=round((breached_count / num_paths) * 100, 1),
            )
        )

    return projections


def _solve_sustainable_withdrawal(
    *,
    initial_capital: float,
    years: int,
    annual_return_pct: float,
    inflation_rate_pct: float,
    other_income_annual: float,
    capital_gains_tax_rate_pct: float,
    embedded_gain_ratio_pct: float,
    schedule: DecumulationSchedule | None = None,
) -> float:
    """Constant real net spending sustainable over ``years``.

    The capital left at the end (the higher of the floor and the bottom of the
    terminal range), one-off expenses and pension are valued in today's money
    and discounted at the real rate: the terminal capital and one-offs reduce
    the spendable capital, the pension is spread evenly over the horizon.
    """
    schedule = schedule or DecumulationSchedule()
    if initial_capital <= 0 or years <= 0:
        return max(0.0, other_income_annual)

    nominal = annual_return_pct / 100.0
    inflation = inflation_rate_pct / 100.0
    real_rate = ((1 + nominal) / (1 + inflation)) - 1

    def discount(year: int) -> float:
        return 1.0 if abs(real_rate) < 1e-9 else (1 + real_rate) ** (-year)

    if abs(real_rate) < 1e-9:
        annuity_factor = float(years)
    else:
        annuity_factor = (1 - (1 + real_rate) ** (-years)) / real_rate
    if annuity_factor <= 0:
        return max(0.0, other_income_annual)

    terminal_pv = schedule.required_terminal_capital * discount(years)
    one_off_pv = sum(amount * discount(year) for year, amount in schedule.one_off_by_year.items())
    spendable_capital = max(0.0, initial_capital - terminal_pv - one_off_pv)
    gross_portfolio_withdrawal = spendable_capital / annuity_factor

    pension_pv = 0.0
    if schedule.pension_start_year is not None:
        pension_pv = sum(schedule.pension_annual * discount(year) for year in range(schedule.pension_start_year, years + 1))

    tax_drag = (max(0.0, capital_gains_tax_rate_pct) / 100.0) * (max(0.0, embedded_gain_ratio_pct) / 100.0)
    keep_rate = max(0.0, 1.0 - tax_drag)
    sustainable_net_portfolio = gross_portfolio_withdrawal * keep_rate
    return max(0.0, sustainable_net_portfolio + pension_pv / annuity_factor + max(0.0, other_income_annual))


def _estimate_embedded_gain_ratio(capital: float, cost_basis: float) -> float:
    if capital <= 0:
        return 0.0
    return max(0.0, min(1.0, (capital - max(0.0, cost_basis)) / capital))


def _solve_gross_sale_for_net_need(net_needed_from_portfolio: float, embedded_gain_ratio: float, tax_rate: float) -> float:
    if net_needed_from_portfolio <= 0:
        return 0.0

    keep_rate = 1.0 - max(0.0, embedded_gain_ratio) * max(0.0, tax_rate)
    if keep_rate <= 1e-9:
        return net_needed_from_portfolio
    return net_needed_from_portfolio / keep_rate


def _empty_monte_carlo_response(portfolio_id: int, portfolio_ids: list[int] | None = None) -> MonteCarloProjectionResponse:
    return MonteCarloProjectionResponse(
        portfolio_id=portfolio_id,
        portfolio_ids=portfolio_ids,
        num_simulations=0,
        horizons=PROJECTION_HORIZONS,
        projections=[],
        annualized_mean_return_pct=0.0,
        annualized_volatility_pct=0.0,
    )


def _empty_decumulation_fields(
    *,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    current_age: int | None,
    schedule: DecumulationSchedule,
) -> dict:
    inflation = max(0.0, inflation_rate_pct) / 100.0
    base_other_income = max(0.0, other_income_annual)
    projections = []
    for year in range(1, years + 1):
        inflation_factor = (1 + inflation) ** (year - 1)
        income = base_other_income + _schedule_income(schedule, year, inflation_factor)
        one_off = schedule.one_off_by_year.get(year, 0.0) * inflation_factor
        projections.append(
            DecumulationYearProjection(
                year=year,
                age=(current_age + year) if current_age else None,
                target_net_spending=round(max(0.0, annual_withdrawal) * inflation_factor + one_off, 2),
                gross_withdrawal=0.0,
                estimated_taxes=0.0,
                net_withdrawal=0.0,
                other_income=round(income, 2),
                net_spending_after_tax=round(income, 2),
                p25_ending_capital=0.0,
                p50_ending_capital=0.0,
                p75_ending_capital=0.0,
                p50_effective_withdrawal_rate_pct=0.0,
                depletion_probability_pct=100.0,
                capital_floor=round(schedule.capital_floor * (1 + inflation) ** year, 2),
                floor_breach_probability_pct=100.0,
            )
        )
    return {
        "initial_capital": 0.0,
        "num_simulations": 0,
        "annualized_mean_return_pct": 0.0,
        "annualized_volatility_pct": 0.0,
        "sustainable_withdrawal": round(base_other_income, 2),
        "success_rate_pct": 0.0,
        "depletion_probability_pct": 100.0,
        "floor_breach_probability_pct": 100.0,
        "p25_terminal_value": 0.0,
        "p50_terminal_value": 0.0,
        "p75_terminal_value": 0.0,
        "depletion_year_p50": 1 if years > 0 else None,
        "floor_breach_year_p50": 1 if years > 0 else None,
        "p50_terminal_value_real": 0.0,
        **_terminal_range_probabilities([0.0], schedule, inflation_rate_pct, years),
        "projections": projections,
    }
