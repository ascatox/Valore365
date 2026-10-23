import pytest

from app.models import FireOneOffExpense, UserSettingsUpdate
from app.services.portfolio_doctor._monte_carlo import (
    DecumulationSchedule,
    _build_decumulation_projections,
    _build_decumulation_schedule,
    _simulate_decumulation_paths,
    _solve_sustainable_withdrawal,
)


def _run_deterministic(*, schedule: DecumulationSchedule, annual_withdrawal: float, years: int, inflation_rate_pct: float = 0.0, mu: float = 0.0):
    paths = _simulate_decumulation_paths(
        initial_capital=1_000_000,
        initial_cost_basis=1_000_000,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=0.0,
        capital_gains_tax_rate_pct=0.0,
        mu_annual=mu,
        sigma_annual=0.0,
        schedule=schedule,
    )
    return paths, _build_decumulation_projections(paths=paths, years=years, other_income_annual=0.0, current_age=60)


def test_schedule_maps_ages_to_plan_years():
    schedule = _build_decumulation_schedule(
        years=30,
        current_age=60,
        capital_floor=700_000,
        pension_annual=20_000,
        pension_start_age=67,
        one_off_expenses=[(60, 10_000), (65, 30_000), (65, 5_000), (59, 1_000), (95, 1_000)],
    )

    assert schedule.pension_start_year == 8
    assert schedule.one_off_by_year == {1: 10_000, 6: 35_000}


def test_schedule_drops_pension_and_one_offs_without_current_age():
    schedule = _build_decumulation_schedule(
        years=30,
        current_age=None,
        capital_floor=0,
        pension_annual=20_000,
        pension_start_age=67,
        one_off_expenses=[(65, 30_000)],
    )

    assert schedule.pension_start_year is None
    assert schedule.pension_annual == 0
    assert schedule.one_off_by_year == {}


def test_pension_without_start_age_applies_from_first_year():
    schedule = _build_decumulation_schedule(
        years=10, current_age=None, capital_floor=0, pension_annual=12_000, pension_start_age=None, one_off_expenses=None,
    )

    assert schedule.pension_start_year == 1


def test_capital_floor_is_indexed_and_breach_is_tracked():
    schedule = DecumulationSchedule(capital_floor=700_000)
    _paths, projections = _run_deterministic(schedule=schedule, annual_withdrawal=50_000, years=10, inflation_rate_pct=2.0)

    assert projections[0].capital_floor == pytest.approx(714_000)
    assert projections[-1].capital_floor == pytest.approx(700_000 * 1.02 ** 10, rel=1e-6)
    breach_year = next(p.year for p in projections if p.floor_breach_probability_pct == 100)
    assert projections[breach_year - 1].p50_ending_capital < projections[breach_year - 1].capital_floor
    assert all(p.floor_breach_probability_pct == 0 for p in projections[: breach_year - 1])
    assert all(p.depletion_probability_pct == 0 for p in projections)


def test_pension_reduces_withdrawals_from_start_year():
    schedule = DecumulationSchedule(pension_annual=20_000, pension_start_year=3)
    _paths, projections = _run_deterministic(schedule=schedule, annual_withdrawal=50_000, years=4)

    assert [p.gross_withdrawal for p in projections] == [50_000, 50_000, 30_000, 30_000]
    assert [p.other_income for p in projections] == [0, 0, 20_000, 20_000]
    assert projections[2].net_spending_after_tax == 50_000


def test_one_off_expense_is_added_to_its_year():
    schedule = DecumulationSchedule(one_off_by_year={2: 40_000})
    _paths, projections = _run_deterministic(schedule=schedule, annual_withdrawal=50_000, years=3)

    assert [p.gross_withdrawal for p in projections] == [50_000, 90_000, 50_000]
    assert projections[1].target_net_spending == 90_000


def test_sustainable_withdrawal_preserves_capital_floor():
    base_kwargs = dict(
        initial_capital=1_000_000,
        years=30,
        annual_return_pct=0.0,
        inflation_rate_pct=0.0,
        other_income_annual=0.0,
        capital_gains_tax_rate_pct=0.0,
        embedded_gain_ratio_pct=0.0,
    )

    assert _solve_sustainable_withdrawal(**base_kwargs) == pytest.approx(1_000_000 / 30)
    assert _solve_sustainable_withdrawal(**base_kwargs, schedule=DecumulationSchedule(capital_floor=700_000)) == pytest.approx(10_000)
    assert _solve_sustainable_withdrawal(
        **base_kwargs, schedule=DecumulationSchedule(capital_floor=700_000, one_off_by_year={5: 60_000})
    ) == pytest.approx(8_000)
    assert _solve_sustainable_withdrawal(
        **base_kwargs, schedule=DecumulationSchedule(capital_floor=700_000, pension_annual=15_000, pension_start_year=11)
    ) == pytest.approx(10_000 + 15_000 * 20 / 30)


def test_settings_accept_one_off_expenses():
    payload = UserSettingsUpdate(
        fire_capital_floor=700_000,
        fire_one_off_expenses=[{"age": 55, "amount": 30_000, "label": "Auto"}],
    )

    assert payload.fire_one_off_expenses == [FireOneOffExpense(age=55, amount=30_000, label="Auto")]
    with pytest.raises(ValueError):
        UserSettingsUpdate(fire_one_off_expenses=[{"age": 55, "amount": 0}])
