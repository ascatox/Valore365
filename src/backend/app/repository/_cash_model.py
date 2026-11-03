"""Cash model shared by the historical valuation and the performance flows (TASK-46).

One rule set, used both by the valuation fold
(``TransactionsMixin.get_portfolio_values_in_range_multi``) and by the external
cashflows that TWR/MWR read (``PerformanceService``), so the value series and
the flows can never disagree:

- buy: cash -= price x quantity + fees + taxes
- sell: cash += price x quantity - fees - taxes (proceeds stay in cash until an
  explicit withdrawal; a sell is never an external flow)
- deposit, dividend, interest: cash += amount
- withdrawal, fee: cash -= amount

Cash is settled at the end of every day (the valuation is end-of-day): if the
day leaves it below zero, the shortfall is an **implicit external
contribution** on that day and cash floors at 0. It never goes negative. This
covers a buy beyond the available cash (no deposit recorded: every buy is fully
an implicit contribution, the old buy/sell fallback) and, symmetrically, a
withdrawal or fee larger than the cash: the uncovered part is money that was
never recorded as entering the portfolio, so it is contributed implicitly and
the net external outflow of the day equals the cash actually there.

The opening ``portfolios.cash_balance`` is not part of the history (it has no
date) and is not used here, as before.
"""

from __future__ import annotations

# Below this, a negative end-of-day balance is float noise, not a shortfall.
_EPS = 1e-6

TRADE_SIDES = frozenset({"buy", "sell"})
CASH_IN_SIDES = frozenset({"deposit", "dividend", "interest"})
CASH_OUT_SIDES = frozenset({"withdrawal", "fee"})


def cash_delta(side: str, gross_base: float, costs_base: float) -> float:
    """Change of cash for one transaction, amounts already in base currency.

    ``gross_base`` is quantity x price, ``costs_base`` fees + taxes (applied
    to buys and sells only, like the external cashflow list).
    """
    if side == "buy":
        return -(gross_base + costs_base)
    if side == "sell":
        return gross_base - costs_base
    if side in CASH_IN_SIDES:
        return gross_base
    if side in CASH_OUT_SIDES:
        return -gross_base
    return 0.0


def cash_delta_from_signed(side: str, signed_amount: float) -> float:
    """Same as cash_delta, from a CashFlowEntry amount (portfolio perspective).

    The entry signs a buy as +cost and a sell as -proceeds (money the
    investor puts in / takes out when trades are flows), so for trades the
    cash moves the opposite way; every other side moves cash by its amount.
    """
    if side in TRADE_SIDES:
        return -float(signed_amount)
    if side in CASH_IN_SIDES or side in CASH_OUT_SIDES:
        return float(signed_amount)
    return 0.0


def settle_day(cash: float) -> tuple[float, float]:
    """End-of-day settlement: (cash floored at 0, implicit contribution >= 0)."""
    if cash < 0:
        shortfall = -cash
        return 0.0, (shortfall if shortfall > _EPS else 0.0)
    return cash, 0.0
