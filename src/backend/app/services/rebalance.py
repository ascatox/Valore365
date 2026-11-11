"""Rebalancing plan: pure, order-independent computation (TASK-39 / V365-003).

Shared by the REST preview (``routes_rebalancing.rebalance_preview``) and the
copilot/MCP tool ``calculate_rebalance_orders``.

Algorithm
---------
1. ``base`` = value of the holdings with a target (+ holdings without a target
   when ``include_untargeted_in_base``) + cash (portfolio cash + extra cash,
   when ``include_cash_in_base``).
2. For every targeted holding: ``target_value = target_weight × base`` and
   ``delta = target_value - current_value``. All deltas are computed against
   the same base before any order is sized, so the result does not depend on
   the iteration order of the targets.
3. Tolerance band (``tolerance_pp``, absolute percentage points on the
   weight) as a trigger: if no tradable holding drifts more than the band
   there are no orders; otherwise every holding is brought to target (so
   sell proceeds are not left idle because a buy is just inside the band).
4. Sells first (never more than the position value); their proceeds are added
   to the cash.
5. Buys are funded by cash + sell proceeds; when the needs exceed the
   available cash they are scaled down proportionally. Cash never goes
   negative. Fees and taxes are not modelled.

Holdings without a target are never traded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Iterable, Literal

RebalanceMode = Literal["buy_only", "rebalance", "sell_only"]
REBALANCE_MODES: tuple[str, ...] = ("buy_only", "rebalance", "sell_only")
DEFAULT_TOLERANCE_PP = 0.5
_EPS = 1e-9


@dataclass(frozen=True)
class RebalanceHolding:
    key: Hashable
    symbol: str
    current_value: float
    target_weight_pct: float | None = None
    # False: kept in the base and in the weights, but never traded
    # (e.g. no price available).
    tradable: bool = True


@dataclass(frozen=True)
class RebalanceOrder:
    key: Hashable
    symbol: str
    side: Literal["buy", "sell"]
    amount: float
    current_weight_pct: float
    target_weight_pct: float
    weight_after_pct: float

    @property
    def drift_pct(self) -> float:
        return self.current_weight_pct - self.target_weight_pct


@dataclass(frozen=True)
class RebalanceWeight:
    key: Hashable
    symbol: str
    current_weight_pct: float
    target_weight_pct: float
    weight_after_pct: float


@dataclass(frozen=True)
class RebalancePlan:
    mode: str
    orders: list[RebalanceOrder]
    weights: list[RebalanceWeight]
    base_value: float
    portfolio_cash: float
    extra_cash: float
    sells_total: float
    buys_total: float
    cash_after: float
    target_sum_pct: float
    untargeted_symbols: list[str] = field(default_factory=list)
    untargeted_value: float = 0.0
    buys_scaled: bool = False

    @property
    def cash_before(self) -> float:
        return self.portfolio_cash + self.extra_cash

    @property
    def unallocated_target_pct(self) -> float:
        return max(100.0 - self.target_sum_pct, 0.0)


def _sort_key(h: RebalanceHolding) -> tuple[str, str]:
    return (str(h.symbol), str(h.key))


def compute_rebalance_plan(
    holdings: Iterable[RebalanceHolding],
    *,
    portfolio_cash: float = 0.0,
    extra_cash: float = 0.0,
    mode: str = "rebalance",
    tolerance_pp: float = DEFAULT_TOLERANCE_PP,
    include_cash_in_base: bool = True,
    include_untargeted_in_base: bool = False,
    max_orders: int | None = None,
    buy_only_deploy_all_cash: bool = False,
) -> RebalancePlan:
    """Compute a rebalancing plan. Pure function, no I/O.

    ``buy_only_deploy_all_cash``: in ``buy_only`` mode spread all the
    available cash across the under-weight holdings proportionally to their
    need, even beyond the target (legacy behaviour of the REST preview).
    ``max_orders``: keep only the N candidates with the largest drift
    (ties broken by symbol) before sizing, so the plan stays funded.
    """
    if mode not in REBALANCE_MODES:
        raise ValueError(f"mode non valida: {mode}")
    portfolio_cash = max(float(portfolio_cash or 0.0), 0.0)
    extra_cash = max(float(extra_cash or 0.0), 0.0)
    cash = portfolio_cash + extra_cash
    tolerance_pp = max(float(tolerance_pp or 0.0), 0.0)

    ordered = sorted(holdings, key=_sort_key)
    targeted = [h for h in ordered if h.target_weight_pct is not None]
    untargeted = [h for h in ordered if h.target_weight_pct is None]
    untargeted_value = sum(max(float(h.current_value), 0.0) for h in untargeted)
    target_sum = sum(float(h.target_weight_pct) for h in targeted)  # type: ignore[arg-type]

    base = sum(max(float(h.current_value), 0.0) for h in targeted)
    if include_untargeted_in_base:
        base += untargeted_value
    if include_cash_in_base:
        base += cash

    def _empty(weights: list[RebalanceWeight]) -> RebalancePlan:
        return RebalancePlan(
            mode=mode, orders=[], weights=weights, base_value=base,
            portfolio_cash=portfolio_cash, extra_cash=extra_cash,
            sells_total=0.0, buys_total=0.0, cash_after=cash, target_sum_pct=target_sum,
            untargeted_symbols=[h.symbol for h in untargeted], untargeted_value=untargeted_value,
        )

    if base <= _EPS or not targeted:
        return _empty([
            RebalanceWeight(h.key, h.symbol, 0.0, float(h.target_weight_pct), 0.0)  # type: ignore[arg-type]
            for h in targeted
        ])

    # 1. Deltas, all against the same base (order independent).
    rows = []
    for h in targeted:
        value = max(float(h.current_value), 0.0)
        target_w = float(h.target_weight_pct)  # type: ignore[arg-type]
        current_w = value / base * 100.0
        drift = current_w - target_w
        delta = target_w / 100.0 * base - value
        rows.append({"h": h, "value": value, "cw": current_w, "tw": target_w, "drift": drift, "delta": delta})

    # 2. Candidates, filtered by mode. The tolerance band is a trigger: when
    #    at least one tradable holding (on the mode's side) drifts more than
    #    the band, every holding of that side is brought to target;
    #    otherwise there are no orders.
    eligible = []
    for r in rows:
        if not r["h"].tradable or abs(r["delta"]) <= _EPS:
            continue
        side = "buy" if r["delta"] > 0 else "sell"
        if mode == "buy_only" and side != "buy":
            continue
        if mode == "sell_only" and side != "sell":
            continue
        if side == "sell" and r["value"] <= _EPS:
            continue
        r["side"] = side
        eligible.append(r)
    triggered = any(abs(r["drift"]) > tolerance_pp + _EPS for r in eligible)
    candidates = eligible if triggered else []
    if max_orders is not None:
        candidates.sort(key=lambda r: (-abs(r["drift"]), str(r["h"].symbol), str(r["h"].key)))
        candidates = candidates[: max(int(max_orders), 0)]

    # 3. Sells first: proceeds fund the buys.
    amounts: dict[int, float] = {}
    sells_total = 0.0
    for r in candidates:
        if r["side"] == "sell":
            amount = min(r["value"], -r["delta"])
            amounts[id(r)] = amount
            sells_total += amount

    # 4. Buys, scaled down proportionally when cash is not enough.
    available = cash + sells_total
    buy_rows = [r for r in candidates if r["side"] == "buy"]
    need_total = sum(r["delta"] for r in buy_rows)
    buys_scaled = False
    if need_total > _EPS:
        scale = available / need_total
        if not (mode == "buy_only" and buy_only_deploy_all_cash):
            if scale < 1.0 - _EPS:
                buys_scaled = True
            scale = min(scale, 1.0)
        for r in buy_rows:
            amounts[id(r)] = r["delta"] * scale
    buys_total = sum(amounts[id(r)] for r in buy_rows)
    cash_after = max(available - buys_total, 0.0)

    # 5. Weights after the plan, on the same basis.
    new_values = {id(r): r["value"] for r in rows}
    for r in candidates:
        amount = amounts.get(id(r), 0.0)
        new_values[id(r)] += amount if r["side"] == "buy" else -amount
    base_after = sum(new_values.values())
    if include_untargeted_in_base:
        base_after += untargeted_value
    if include_cash_in_base:
        base_after += cash_after

    def _after(r: dict) -> float:
        return new_values[id(r)] / base_after * 100.0 if base_after > _EPS else 0.0

    orders = [
        RebalanceOrder(
            key=r["h"].key, symbol=r["h"].symbol, side=r["side"], amount=amounts[id(r)],
            current_weight_pct=r["cw"], target_weight_pct=r["tw"], weight_after_pct=_after(r),
        )
        for r in candidates
        if amounts.get(id(r), 0.0) > _EPS
    ]
    orders.sort(key=lambda o: (0 if o.side == "sell" else 1, -o.amount, str(o.symbol), str(o.key)))
    weights = [RebalanceWeight(r["h"].key, r["h"].symbol, r["cw"], r["tw"], _after(r)) for r in rows]

    return RebalancePlan(
        mode=mode, orders=orders, weights=weights, base_value=base,
        portfolio_cash=portfolio_cash, extra_cash=extra_cash,
        sells_total=sells_total, buys_total=buys_total, cash_after=cash_after,
        target_sum_pct=target_sum, untargeted_symbols=[h.symbol for h in untargeted],
        untargeted_value=untargeted_value, buys_scaled=buys_scaled,
    )


# ---------------------------------------------------------------------------
# Current weights against the targets (TASK-85)
# ---------------------------------------------------------------------------

TARGET_WEIGHT_BASIS_NOTE = (
    "Pesi attuali sul valore degli strumenti con un peso obiettivo piu' la liquidita' del "
    "portafoglio (stesso modello della performance), la stessa base di calculate_rebalance_orders "
    "e calculate_pac_contribution: total_value = valore degli strumenti con target + cash_balance. "
    "Le posizioni senza target restano fuori dal totale. Il peso di get_positions e' invece sul "
    "valore delle sole posizioni."
)


@dataclass(frozen=True)
class TargetWeights:
    """Current weight of every targeted instrument on the rebalancing base."""

    base_value: float
    cash: float
    by_key: dict[Hashable, RebalanceWeight]
    untargeted_symbols: list[str] = field(default_factory=list)
    untargeted_value: float = 0.0

    def current_weight_pct(self, key: Hashable) -> float:
        w = self.by_key.get(key)
        return w.current_weight_pct if w is not None else 0.0


def target_holdings(positions: Iterable, target_alloc: Iterable) -> list[RebalanceHolding]:
    """Holdings for the rebalancing algorithm: every position (target or not)
    plus the targeted assets not held yet (value 0). ``positions`` need
    ``asset_id``, ``symbol``, ``market_value``; targets ``asset_id``,
    ``symbol``, ``weight_pct``."""
    targets = {t.asset_id: t for t in target_alloc}
    held = set()
    holdings: list[RebalanceHolding] = []
    for p in positions:
        held.add(p.asset_id)
        holdings.append(RebalanceHolding(
            key=p.asset_id, symbol=p.symbol, current_value=float(p.market_value or 0.0),
            target_weight_pct=float(targets[p.asset_id].weight_pct) if p.asset_id in targets else None,
        ))
    holdings += [
        RebalanceHolding(key=t.asset_id, symbol=t.symbol, current_value=0.0, target_weight_pct=float(t.weight_pct))
        for t in targets.values()
        if t.asset_id not in held
    ]
    return holdings


def current_target_weights(positions: Iterable, target_alloc: Iterable, cash: float) -> TargetWeights:
    """Single source of the current weights shown by get_target_drift, the PAC
    and calculate_rebalance_orders (TASK-85): the base of
    ``compute_rebalance_plan`` with the portfolio cash and no extra cash
    (targeted holdings + cash; holdings without a target excluded)."""
    plan = compute_rebalance_plan(target_holdings(positions, target_alloc), portfolio_cash=cash)
    return TargetWeights(
        base_value=plan.base_value,
        cash=plan.portfolio_cash,
        by_key={w.key: w for w in plan.weights},
        untargeted_symbols=list(plan.untargeted_symbols),
        untargeted_value=plan.untargeted_value,
    )
