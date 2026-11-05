"""Scenario Lab: pure what-if simulator over a Doctor snapshot (contract §8).

``preview_scenario(snapshot, request, *, policy_document, repo=None)`` and
``compare_scenarios(snapshot, requests, *, policy_document, repo=None)``
never write anything: they copy the snapshot holdings, apply simulated
purchases/sales and evaluate the result with **the same**
``compute_metrics`` + ``build_evaluation_response`` (``evaluate_policy``)
used for the baseline, on a simulated snapshot built by
``snapshot_from_holdings``. ``repo`` (optional) is only read, by the metrics
(ETF enrichment / TER metadata), exactly as for the baseline.

Pipeline for each scenario:
1. resolve the assets of the request (only assets already in the scope: the
   classification inputs of a new asset are not known, MVP) — unknown asset
   -> ``InvalidRequest`` 400;
2. check that the constraints can be satisfied (cash, no-sell, turnover,
   equity total); when they cannot the result is ``feasible = false`` with a
   reason (and ``required_new_cash`` when more cash would solve it) and no
   invented "after" state;
3. build the simulated holdings, reconcile totals and cash;
4. evaluate before/after on the same methodology and compare the rules.

Modes (MVP, gross of taxes, D07):
- ``manual``: buy/sell amounts per asset. Funded by ``new_cash`` + net sale
  proceeds (+ the cash balance with ``constraints.use_cash_balance``);
  unspent funds stay in the cash balance.
- ``new_cash_only``: no sales; new cash bought pro rata to the current values
  (water-filling) without exceeding the maximum weights: ``target_weights``
  (asset_id -> max pct) or, when absent, the max of the enabled
  ``max_single_position_pct`` policy rule (applied to every canonical
  security). Required cash: ``max(0, H/p − V)`` (+ costs). With
  ``keep_equity_total`` the cash is split by asset-class bucket
  (equity / unknown / other) in proportion to the current values, so the
  equity weight is unchanged, or the scenario is infeasible.
- ``rebalance``: listed assets go to exactly their target weight of the
  final invested value, unlisted assets share the rest pro rata to their
  current values; new cash is fully invested. ``no_sell`` makes it
  infeasible when a sale would be needed (required cash given when cash can
  solve it); ``max_turnover_pct`` caps the turnover.

Turnover = (Σ purchases + Σ sales) / (2 × invested value before) × 100.
Costs: per operation ``fee_model.pct`` % of the amount + ``fee_model.fixed``.
Aggregate scopes: overall weights only, never per-account orders.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from ...schemas.doctor_policy import (
    DataQuality,
    MetricValueRead,
    PolicyScope,
    RuleResult,
)
from ...schemas.doctor_scenario import (
    SCENARIO_DISCLAIMER,
    RuleChange,
    ScenarioChange,
    ScenarioCompareRequest,
    ScenarioComparison,
    ScenarioCosts,
    ScenarioInput,
    ScenarioRankItem,
    ScenarioRequest,
    ScenarioResult,
    ScenarioSide,
    VolatilityEstimate,
)
from ..asset_classification import EQUITY, UNKNOWN
from ..portfolio_doctor._holdings import AnalyzedHolding
from .errors import DoctorPolicyError, InvalidRequest
from .evaluator import build_evaluation_response
from .metrics import (
    METHODOLOGY_VERSION,
    ClassificationMemo,
    canonical_key,
    compute_metrics,
    format_it,
    format_threshold_it,
)
from .scope import build_scope
from .snapshot import DoctorSnapshot, is_cash_holding, snapshot_from_holdings
from .validator import normalize_policy_document

MONEY_TOL = 1e-6  # base currency
WEIGHT_TOL = 1e-6  # percentage points
MIN_TRADE = 0.01  # a purchase below one cent is not an operation (water-filling)
# Refinements of the minimum new cash with per-operation costs (new_cash_only).
MAX_REQUIRED_CASH_ITERATIONS = 20
MAX_FIXED_POINT_ITERATIONS = 200

VOLATILITY_BEFORE_REASON = (
    "Volatilità non calcolata nel Lab: è disponibile nell'analisi Doctor del portafoglio."
)
VOLATILITY_AFTER_REASON = (
    "N/D: la volatilità dopo lo scenario richiederebbe lo storico dei prezzi con i pesi simulati; "
    "non viene stimata e non viene riutilizzata quella attuale."
)


class SnapshotChanged(DoctorPolicyError):
    """409: the portfolio changed since the snapshot the client is looking at."""

    code = "snapshot_changed"
    status_code = 409
    retryable = True


class _Infeasible(Exception):
    def __init__(self, code: str, reason: str, *, required_new_cash: float | None = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.required_new_cash = required_new_cash


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def _field_errors(exc: ValidationError) -> list[dict[str, str]]:
    out = []
    for err in exc.errors():
        loc = ""
        for part in err.get("loc", ()):
            loc += f"[{part}]" if isinstance(part, int) else (f".{part}" if loc else str(part))
        out.append({"field": loc or "body", "code": str(err.get("type", "invalid")), "message": str(err.get("msg", ""))})
    return out


def _parse(model: type[BaseModel], payload: Any) -> Any:
    if isinstance(payload, model):
        return payload
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    if not isinstance(payload, Mapping):
        raise InvalidRequest("Il corpo della richiesta deve essere un oggetto JSON")
    data = dict(payload)
    if "portfolio_ids" not in data and "portfolio_id" in data and "portfolio_ids" in model.model_fields:
        data["portfolio_ids"] = [data.pop("portfolio_id")]
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise InvalidRequest("Richiesta di scenario non valida", field_errors=_field_errors(exc)) from exc


def parse_scenario_request(payload: Any) -> ScenarioRequest:
    """Strict ``ScenarioRequest`` from a JSON body (400 ``invalid_request`` on error)."""
    return _parse(ScenarioRequest, payload)


def parse_compare_request(payload: Any) -> ScenarioCompareRequest:
    return _parse(ScenarioCompareRequest, payload)


def _as_input(request: Any) -> ScenarioInput:
    if isinstance(request, ScenarioInput):
        return request
    if isinstance(request, Mapping) and ("portfolio_ids" in request or "portfolio_id" in request):
        return parse_scenario_request(request)
    return _parse(ScenarioInput, request)


def scenario_input_hash(request: ScenarioInput) -> str:
    """sha256 of the canonical scenario inputs (scope and snapshot excluded)."""
    data = request.model_dump(mode="json", exclude={"portfolio_ids", "snapshot_id", "policy_version"})
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------


def _money_it(value: float) -> str:
    text = f"{value:,.0f}".replace(",", ".")
    return f"{text} €"


def _ceil_cents(value: float) -> float:
    if value <= MONEY_TOL:
        return 0.0
    # Tiny relative slack so 227028.5714 -> 227028.58, not 227028.59 from float noise.
    return math.ceil(round(value * 100.0, 6)) / 100.0


# ---------------------------------------------------------------------------
# book of the snapshot
# ---------------------------------------------------------------------------


@dataclass
class _Book:
    """Tradable (non-cash) holdings of the snapshot keyed by asset_id."""

    by_id: dict[int, AnalyzedHolding]
    values: dict[int, float]
    cash: float
    # Classification memo of this request (shared by the before/after metrics).
    memo: ClassificationMemo = field(default_factory=ClassificationMemo)

    @property
    def invested(self) -> float:
        return sum(self.values.values())

    @property
    def ids(self) -> list[int]:
        return sorted(self.values)


def _book(snapshot: DoctorSnapshot) -> _Book:
    by_id: dict[int, AnalyzedHolding] = {}
    values: dict[int, float] = {}
    for h in sorted(snapshot.holdings, key=lambda x: (int(x.asset_id), x.symbol)):
        if is_cash_holding(h):
            continue
        aid = int(h.asset_id)
        values[aid] = values.get(aid, 0.0) + max(0.0, float(h.market_value or 0.0))
        by_id.setdefault(aid, h)
    return _Book(by_id=by_id, values=values, cash=float(snapshot.cash_value or 0.0))


def _resolve(book: _Book, *, asset_id: int | None, symbol: str | None, field_name: str) -> int:
    if asset_id is not None:
        if asset_id not in book.by_id:
            raise InvalidRequest(
                "Asset non presente nel portafoglio",
                field_errors=[{
                    "field": field_name, "code": "unknown_asset",
                    "message": "Nel Lab sono ammessi solo strumenti già presenti nello scope (MVP)",
                }],
            )
        if symbol and book.by_id[asset_id].symbol.strip().upper() != symbol.strip().upper():
            raise InvalidRequest(
                "symbol e asset_id non corrispondono",
                field_errors=[{"field": field_name, "code": "inconsistent", "message": "symbol e asset_id non corrispondono"}],
            )
        return asset_id
    wanted = (symbol or "").strip().upper()
    matches = [aid for aid, h in book.by_id.items() if (h.symbol or "").strip().upper() == wanted]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise InvalidRequest(
            "Simbolo ambiguo",
            field_errors=[{"field": field_name, "code": "ambiguous", "message": "Più strumenti con questo simbolo: usa asset_id"}],
        )
    raise InvalidRequest(
        "Asset non presente nel portafoglio",
        field_errors=[{
            "field": field_name, "code": "unknown_asset",
            "message": "Nel Lab sono ammessi solo strumenti già presenti nello scope (MVP)",
        }],
    )


MAX_ASSET_ID_DIGITS = 18  # fits a bigint


def _resolve_weights(book: _Book, weights: Mapping[str, float]) -> dict[int, float]:
    """target_weights keys (asset_id as string, or symbol) -> asset_id: fraction."""
    out: dict[int, float] = {}
    for key in sorted(weights):
        field_name = f"target_weights.{key}"
        raw = str(key).strip()
        # isdigit() alone accepts "²" or other Unicode digits that int() rejects
        # (or maps to an unrelated id): only short ASCII digit strings are ids,
        # anything else is looked up as a symbol (-> 400 unknown_asset).
        if raw.isascii() and raw.isdigit() and len(raw) <= MAX_ASSET_ID_DIGITS:
            aid = _resolve(book, asset_id=int(raw), symbol=None, field_name=field_name)
        else:
            aid = _resolve(book, asset_id=None, symbol=raw, field_name=field_name)
        if aid in out:
            raise InvalidRequest(
                "Peso obiettivo duplicato",
                field_errors=[{"field": field_name, "code": "duplicate", "message": "Asset già indicato"}],
            )
        out[aid] = float(weights[key]) / 100.0
    return out


# ---------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------


@dataclass
class _Plan:
    buys: dict[int, float] = field(default_factory=dict)
    sells: dict[int, float] = field(default_factory=dict)
    fees: dict[int, float] = field(default_factory=dict)
    variable_cost: float = 0.0
    fixed_cost: float = 0.0
    operations: int = 0
    cash_after: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def add_fee(self, aid: int, amount: float, fee_model: Any) -> float:
        if amount <= MONEY_TOL:
            return 0.0
        variable = amount * float(fee_model.pct) / 100.0
        fixed = float(fee_model.fixed)
        self.variable_cost += variable
        self.fixed_cost += fixed
        self.operations += 1
        self.fees[aid] = self.fees.get(aid, 0.0) + variable + fixed
        return variable + fixed

    @property
    def costs(self) -> float:
        return self.variable_cost + self.fixed_cost


def _plan_manual(book: _Book, req: ScenarioInput) -> _Plan:
    if not req.operations:
        raise InvalidRequest(
            "Nessuna operazione indicata",
            field_errors=[{"field": "operations", "code": "required", "message": "Indica almeno un acquisto o una vendita"}],
        )
    _no_weights(req, "manual")
    plan = _Plan()
    resolved = [
        (_resolve(book, asset_id=op.asset_id, symbol=op.symbol, field_name=f"operations[{i}]"), op)
        for i, op in enumerate(req.operations)
    ]
    if req.constraints.no_sell and any(op.action == "sell" for _aid, op in resolved):
        raise _Infeasible("no_sell", "Lo scenario contiene vendite ma il vincolo «nessuna vendita» è attivo.")
    proceeds = 0.0
    spend = 0.0
    for aid, op in resolved:
        fee = plan.add_fee(aid, op.amount, req.fee_model)
        if op.action == "sell":
            plan.sells[aid] = plan.sells.get(aid, 0.0) + op.amount
            proceeds += op.amount - fee
        else:
            plan.buys[aid] = plan.buys.get(aid, 0.0) + op.amount
            spend += op.amount + fee
    for aid, sold in sorted(plan.sells.items()):
        if sold > book.values[aid] + MONEY_TOL:
            raise _Infeasible(
                "oversell",
                f"Vendita di {_money_it(sold)} su {book.by_id[aid].symbol} superiore al valore della posizione "
                f"({_money_it(book.values[aid])}): nessuna posizione corta è ammessa.",
            )
    available = req.new_cash + proceeds + (book.cash if req.constraints.use_cash_balance else 0.0)
    if spend > available + MONEY_TOL:
        shortfall = spend - available
        raise _Infeasible(
            "insufficient_cash",
            f"Gli acquisti ({_money_it(spend)} con i costi) superano la liquidità disponibile "
            f"({_money_it(available)}): mancano {_money_it(shortfall)}.",
            required_new_cash=_ceil_cents(req.new_cash + shortfall),
        )
    plan.cash_after = book.cash + req.new_cash + proceeds - spend
    if plan.cash_after > book.cash + 0.005:
        plan.warnings.append(
            f"Liquidità non investita: {_money_it(plan.cash_after - book.cash)} restano nel saldo di cassa."
        )
    return plan


def _no_weights(req: ScenarioInput, mode: str) -> None:
    if req.target_weights:
        raise InvalidRequest(
            "target_weights non ammessi in questa modalità",
            field_errors=[{"field": "target_weights", "code": "not_allowed", "message": f"Non usato nella modalità {mode}"}],
        )


def _no_operations(req: ScenarioInput, mode: str) -> None:
    if req.operations:
        raise InvalidRequest(
            "operations non ammesse in questa modalità",
            field_errors=[{"field": "operations", "code": "not_allowed", "message": f"Non usato nella modalità {mode}"}],
        )


def _policy_single_cap(policy_document: Mapping[str, Any] | None) -> tuple[float, str] | None:
    """(max fraction, rule label) of the enabled max_single_position_pct rule."""
    if not policy_document:
        return None
    try:
        normalized = normalize_policy_document(dict(policy_document))
    except Exception:
        return None
    for rule in normalized.get("rules", []):
        if (
            rule.get("enabled", True)
            and rule.get("metric_code") == "max_single_position_pct"
            and rule.get("max_value") is not None
        ):
            return float(rule["max_value"]) / 100.0, str(rule.get("label") or rule["rule_id"])
    return None


def _groups(book: _Book) -> dict[str, list[int]]:
    """Canonical security (ISIN, fallback asset_id) -> asset_ids, as in the metrics."""
    out: dict[str, list[int]] = {}
    for aid in book.ids:
        out.setdefault(canonical_key(book.by_id[aid]), []).append(aid)
    return out


def _bucket(holding: AnalyzedHolding, memo: ClassificationMemo) -> str:
    asset_class = memo.policy_asset_class(holding)
    if asset_class == EQUITY:
        return "equity"
    if asset_class == UNKNOWN:
        return "unknown"
    return "other"


def _too_complex() -> InvalidRequest:
    return InvalidRequest(
        "Scenario troppo complesso",
        field_errors=[{
            "field": "new_cash", "code": "too_complex",
            "message": "Scenario troppo complesso da calcolare: riduci il numero di posizioni o i costi fissi per operazione",
        }],
    )


def _water_fill(amount: float, weights: dict[str, float], capacity: dict[str, float]) -> tuple[dict[str, float], float]:
    """Spread ``amount`` pro rata to ``weights`` without exceeding ``capacity``.

    Returns (allocation, unplaced amount).
    """
    alloc = {k: 0.0 for k in weights}
    remaining = amount
    active = sorted(k for k, w in weights.items() if w > 0 and capacity.get(k, math.inf) >= MIN_TRADE)
    while remaining > MONEY_TOL and active:
        total_w = sum(weights[k] for k in active)
        saturated = []
        for k in active:
            share = remaining * weights[k] / total_w
            room = capacity.get(k, math.inf) - alloc[k]
            if share >= room - MONEY_TOL:
                saturated.append(k)
        if not saturated:
            for k in active:
                alloc[k] += remaining * weights[k] / total_w
            remaining = 0.0
            break
        for k in saturated:
            room = capacity[k] - alloc[k]
            alloc[k] += room
            remaining -= room
        done = set(saturated)  # set: the filter stays O(n) per round (was O(n * saturated))
        active = [k for k in active if k not in done]
    return alloc, max(0.0, remaining)


def _plan_new_cash(book: _Book, req: ScenarioInput, policy_document: Mapping[str, Any] | None) -> _Plan:
    _no_operations(req, "new_cash_only")
    plan = _Plan()
    V = book.invested
    C = float(req.new_cash)
    if V <= MONEY_TOL:
        raise _Infeasible(
            "empty_portfolio",
            "Portafoglio senza posizioni investite: non c'è una ripartizione attuale da seguire per il versamento.",
        )
    groups = _groups(book)
    gvalue = {g: sum(book.values[a] for a in ids) for g, ids in groups.items()}

    caps: dict[str, float] = {}
    if req.target_weights:
        for aid, frac in _resolve_weights(book, req.target_weights).items():
            g = canonical_key(book.by_id[aid])
            caps[g] = min(caps.get(g, math.inf), frac)
    else:
        derived = _policy_single_cap(policy_document)
        if derived is not None:
            frac, label = derived
            caps = {g: frac for g in groups}
            plan.warnings.append(
                f"Peso massimo per posizione ricavato dalla tua regola «{label}»: {format_threshold_it(frac * 100)}%."
            )

    # Total invested value needed so every capped security is within its cap: H/p.
    needed_total = V
    impossible: list[str] = []
    for g, cap in sorted(caps.items()):
        if gvalue[g] <= MONEY_TOL:
            continue
        if cap <= 1e-12:
            impossible.append(book.by_id[groups[g][0]].symbol)
            continue
        needed_total = max(needed_total, gvalue[g] / cap)
    if impossible:
        raise _Infeasible(
            "impossible_without_sell",
            "Un peso massimo 0% per " + ", ".join(impossible) + " si raggiunge solo vendendo: "
            "nessun versamento lo rende possibile.",
        )
    required_buys = max(0.0, needed_total - V)

    bucket_of = {g: _bucket(book.by_id[groups[g][0]], book.memo) for g in groups}

    def allocate(total_buys: float) -> dict[int, float]:
        T = V + total_buys
        capacity = {g: max(0.0, caps[g] * T - gvalue[g]) for g in caps}
        if req.constraints.keep_equity_total:
            buckets: dict[str, list[str]] = {}
            for g in sorted(groups):
                buckets.setdefault(bucket_of[g], []).append(g)
            alloc: dict[str, float] = {}
            for name, members in sorted(buckets.items()):
                share = sum(gvalue[g] for g in members) / V
                part, left = _water_fill(total_buys * share, {g: gvalue[g] for g in members}, capacity)
                if left > 0.005:
                    raise _Infeasible(
                        "keep_equity_total",
                        "Con il vincolo «quota azionaria invariata» il versamento va ripartito anche su "
                        f"strumenti della classe {_BUCKET_LABEL[name]}, ma non ce ne sono abbastanza entro i "
                        f"limiti: restano {_money_it(left)} non collocabili.",
                    )
                alloc.update(part)
        else:
            alloc, left = _water_fill(total_buys, dict(gvalue), capacity)
            if left > 0.005:
                raise _Infeasible(
                    "capacity_exceeded",
                    "Non ci sono abbastanza altre posizioni per investire il versamento entro i limiti di peso: "
                    f"restano {_money_it(left)} non collocabili.",
                )
        per_asset: dict[int, float] = {}
        for g, amount in alloc.items():
            if amount <= MONEY_TOL:
                continue
            ids = groups[g]
            gv = gvalue[g]
            for a in ids:
                per_asset[a] = per_asset.get(a, 0.0) + (amount * book.values[a] / gv if gv > 0 else amount / len(ids))
        return per_asset

    pct = float(req.fee_model.pct) / 100.0
    fixed = float(req.fee_model.fixed)

    def cash_for(buys: dict[int, float]) -> float:
        n = sum(1 for v in buys.values() if v > MONEY_TOL)
        return sum(buys.values()) * (1 + pct) + fixed * n

    def invest(cash: float) -> tuple[dict[int, float], float]:
        """Purchases spending ``cash``: B (1 + pct) + fixed * n = cash, n = purchases made."""
        buys: dict[int, float] = {}
        investable = 0.0
        n = len(book.ids)
        for _ in range(10):
            investable = max(0.0, cash - fixed * n) / (1 + pct)
            buys = allocate(investable) if investable > MONEY_TOL else {}
            new_n = sum(1 for v in buys.values() if v > MONEY_TOL)
            if new_n == n:
                break
            n = new_n
        return buys, investable

    # Cash needed to reach the caps (costs included), checked against invest().
    required_cash = cash_for(allocate(required_buys)) if required_buys > MONEY_TOL else 0.0
    if required_cash > 0:
        # Computational bound: each step re-runs invest() (up to 10 water-fills
        # over every security); without a cap a large scope could loop
        # len(book.ids) times. Not converging within the cap is a 400, never
        # an underestimated required_new_cash.
        for _ in range(min(len(book.ids) + 1, MAX_REQUIRED_CASH_ITERATIONS)):
            if invest(_ceil_cents(required_cash))[1] >= required_buys - MONEY_TOL:
                break
            required_cash += max(fixed, 0.01)
        else:
            raise _too_complex()
    if C + MONEY_TOL < required_cash:
        worst = max(
            (g for g in caps if gvalue[g] > MONEY_TOL and caps[g] > 0 and gvalue[g] / caps[g] >= needed_total - MONEY_TOL),
            key=lambda g: (gvalue[g] / caps[g], g),
        )
        symbol = book.by_id[groups[worst][0]].symbol
        raise _Infeasible(
            "insufficient_cash",
            f"Per portare {symbol} dal {format_it(gvalue[worst] / V * 100, 1)}% al "
            f"{format_threshold_it(caps[worst] * 100)}% senza vendere servono almeno "
            f"{_money_it(_ceil_cents(required_cash))} di nuova liquidità (indicati {_money_it(C)}).",
            required_new_cash=_ceil_cents(required_cash),
        )

    if C <= MONEY_TOL:
        plan.cash_after = book.cash
        return plan
    buys, investable = invest(C)
    if investable < required_buys - MONEY_TOL:
        raise _Infeasible(
            "insufficient_cash",
            "Il versamento, al netto dei costi, non basta a rispettare i pesi massimi.",
            required_new_cash=_ceil_cents(required_cash),
        )
    for aid, amount in sorted(buys.items()):
        if amount > MONEY_TOL:
            plan.buys[aid] = amount
            plan.add_fee(aid, amount, req.fee_model)
    plan.cash_after = book.cash + C - sum(plan.buys.values()) - plan.costs
    if plan.cash_after < book.cash - 0.005:
        raise _Infeasible(
            "insufficient_cash", "Il versamento non copre i costi delle operazioni.",
            required_new_cash=_ceil_cents(C + book.cash - plan.cash_after),
        )
    if plan.cash_after > book.cash + 0.005:
        plan.warnings.append(
            f"Liquidità non investita: {_money_it(plan.cash_after - book.cash)} restano nel saldo di cassa."
        )
    return plan


_BUCKET_LABEL = {"equity": "azionaria", "unknown": "non classificata", "other": "non azionaria"}


def _plan_rebalance(book: _Book, req: ScenarioInput) -> _Plan:
    _no_operations(req, "rebalance")
    if not req.target_weights:
        raise InvalidRequest(
            "Pesi obiettivo mancanti",
            field_errors=[{"field": "target_weights", "code": "required", "message": "Indica almeno un peso obiettivo"}],
        )
    targets = _resolve_weights(book, req.target_weights)
    V = book.invested
    unlisted = [a for a in book.ids if a not in targets]
    unlisted_value = sum(book.values[a] for a in unlisted)
    rest = max(0.0, 1.0 - sum(targets.values()))
    if rest > 1e-9 and unlisted_value <= MONEY_TOL:
        raise InvalidRequest(
            "I pesi obiettivo devono sommare a 100",
            field_errors=[{
                "field": "target_weights", "code": "sum_not_100",
                "message": "I pesi coprono tutte le posizioni: la somma deve essere 100",
            }],
        )
    funds = float(req.new_cash) + (book.cash if req.constraints.use_cash_balance else 0.0)
    pct = float(req.fee_model.pct) / 100.0
    fixed = float(req.fee_model.fixed)

    def target_values(T: float) -> dict[int, float]:
        out = {a: targets[a] * T for a in targets}
        for a in unlisted:
            out[a] = rest * T * book.values[a] / unlisted_value if unlisted_value > 0 else 0.0
        return out

    def deltas(T: float) -> dict[int, float]:
        tv = target_values(T)
        return {a: tv[a] - book.values[a] for a in book.ids}

    # T = V + funds − costs(T); the number of trades is fixed from the cost-free solution.
    T = V + funds
    n = sum(1 for d in deltas(T).values() if abs(d) > MONEY_TOL)
    for _ in range(MAX_FIXED_POINT_ITERATIONS):
        new_T = V + funds - pct * sum(abs(d) for d in deltas(T).values()) - fixed * n
        if abs(new_T - T) < 1e-9:
            T = new_T
            break
        T = new_T
    if T <= MONEY_TOL:
        raise _Infeasible("insufficient_cash", "I costi delle operazioni superano il valore da investire.")
    d = deltas(T)

    if req.constraints.no_sell and any(v < -MONEY_TOL for v in d.values()):
        blocked = [a for a in book.ids if book.values[a] > MONEY_TOL and (
            (a in targets and targets[a] <= 1e-12) or (a not in targets and rest <= 1e-12)
        )]
        first_sale = min((a for a in book.ids if d[a] < -MONEY_TOL), key=lambda a: (d[a], a))
        symbol = book.by_id[first_sale].symbol
        if blocked:
            raise _Infeasible(
                "impossible_without_sell",
                "I pesi obiettivo azzerano " + ", ".join(book.by_id[a].symbol for a in blocked)
                + ": si raggiungono solo vendendo, nessun versamento li rende possibili.",
            )
        needed = max(
            [book.values[a] / targets[a] for a in targets if targets[a] > 0]
            + ([unlisted_value / rest] if unlisted_value > 0 and rest > 0 else [])
        )
        buys = {a: max(0.0, v) for a, v in deltas(needed).items()}
        # Every asset with a positive target buys once the cash is a cent above the
        # minimum: count the fixed cost on all of them so the amount is sufficient.
        n_buys = sum(1 for v in target_values(needed).values() if v > MONEY_TOL)
        costs = pct * sum(buys.values()) + fixed * n_buys
        required = max(0.0, needed - V + costs - (book.cash if req.constraints.use_cash_balance else 0.0))
        target_pct = targets.get(first_sale)
        goal = f"al {format_threshold_it(target_pct * 100)}%" if target_pct is not None else "ai pesi obiettivo"
        raise _Infeasible(
            "no_sell",
            f"Per portare {symbol} dal {format_it(book.values[first_sale] / V * 100, 1)}% {goal} senza vendere "
            f"servono almeno {_money_it(_ceil_cents(required))} di nuova liquidità "
            f"(indicati {_money_it(req.new_cash)}).",
            required_new_cash=_ceil_cents(required),
        )

    plan = _Plan()
    for a in book.ids:
        if d[a] > MONEY_TOL:
            plan.buys[a] = d[a]
        elif d[a] < -MONEY_TOL:
            plan.sells[a] = min(-d[a], book.values[a])
        plan.add_fee(a, abs(d[a]), req.fee_model)
    plan.cash_after = (
        book.cash + req.new_cash + sum(plan.sells.values()) - sum(plan.buys.values()) - plan.costs
    )
    return plan


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


def _scope(snapshot: DoctorSnapshot) -> PolicyScope:
    if snapshot.portfolio_ids:
        return build_scope(snapshot.portfolio_ids)
    return PolicyScope(portfolio_ids=[], scope_type="single", fingerprint="p:")


@dataclass
class _State:
    snapshot: DoctorSnapshot
    metrics: dict[str, Any]
    evaluation: Any

    def side(self, volatility_reason: str) -> ScenarioSide:
        return ScenarioSide(
            invested_value=self.snapshot.invested_value,
            cash_value=float(self.snapshot.cash_value),
            total_value=self.snapshot.invested_value + float(self.snapshot.cash_value),
            metrics={code: MetricValueRead(**m.to_dict()) for code, m in self.metrics.items()},
            evaluation_status=self.evaluation.status,
            evaluation_summary=self.evaluation.summary,
            rule_results=list(self.evaluation.results),
            volatility=VolatilityEstimate(reason=volatility_reason),
        )


def _evaluate(
    snapshot: DoctorSnapshot,
    policy_document: Mapping[str, Any] | None,
    repo: Any,
    now: datetime,
    metrics: dict[str, Any] | None = None,
    meta: Mapping[str, Any] | None = None,
    memo: ClassificationMemo | None = None,
) -> _State:
    metrics = metrics if metrics is not None else compute_metrics(snapshot, repo, now=now, memo=memo)
    evaluation = build_evaluation_response(
        dict(policy_document) if policy_document is not None else None,
        snapshot, metrics, repo=repo, now=now, **dict(meta or {}),
    )
    return _State(snapshot=snapshot, metrics=metrics, evaluation=evaluation)


def _simulated_snapshot(snapshot: DoctorSnapshot, book: _Book, values: dict[int, float], cash_after: float) -> DoctorSnapshot:
    holdings = []
    seen: set[int] = set()
    for h in sorted(snapshot.holdings, key=lambda x: (int(x.asset_id), x.symbol)):
        copy = AnalyzedHolding(**h.__dict__)
        copy.weight_pct = 0.0
        if not is_cash_holding(h):
            aid = int(h.asset_id)
            if aid in seen:  # duplicated asset rows are merged in the book
                continue
            seen.add(aid)
            copy.market_value = max(0.0, values[aid])
        holdings.append(copy)
    return snapshot_from_holdings(
        holdings,
        portfolio_ids=snapshot.portfolio_ids,
        base_currency=snapshot.base_currency,
        cash_value=cash_after,
        price_as_of=dict(snapshot.price_as_of),
        stale_asset_ids=set(snapshot.stale_asset_ids),
        missing_price_asset_ids=set(snapshot.missing_price_asset_ids),
        last_successful_price_sync=snapshot.last_successful_price_sync,
        last_sync_status=snapshot.last_sync_status,
        sync_available=snapshot.sync_available,
        freshness_note=snapshot.freshness_note,
    )


def _rule_changes(before: Sequence[RuleResult], after: Sequence[RuleResult]) -> tuple[list[RuleChange], list[RuleChange]]:
    before_by = {r.rule_id: r for r in before}
    resolved, new = [], []
    for r in after:
        b = before_by.get(r.rule_id)
        if b is None:
            continue
        item = RuleChange(
            rule_id=r.rule_id, metric_code=r.metric_code, label=r.label, reason=r.reason,
            before_status=b.status, after_status=r.status, before_actual=b.actual, after_actual=r.actual,
        )
        if b.status == "FAIL" and r.status == "PASS":
            resolved.append(item)
        elif r.status == "FAIL" and b.status != "FAIL":
            new.append(item)
    return resolved, new


def _same_metric(a: Any, b: Any) -> bool:
    for attr in ("value", "lower", "upper"):
        x, y = getattr(a, attr), getattr(b, attr)
        if (x is None) != (y is None):
            return False
        if x is not None and abs(x - y) > WEIGHT_TOL:
            return False
    return True


def _base_warnings(snapshot: DoctorSnapshot, policy_document: Mapping[str, Any] | None) -> list[str]:
    warnings = ["Simulazione al lordo delle imposte (tax_model «none»): costi fiscali non considerati."]
    if len(snapshot.portfolio_ids) > 1:
        warnings.append(
            "Scope aggregato: la simulazione riguarda i pesi complessivi; nessuna indicazione di ordini per "
            "singolo portafoglio o conto."
        )
    if snapshot.data_quality["status"] in ("stale", "partial"):
        warnings.append(
            "Quotazioni non aggiornate o mancanti per parte del portafoglio: i valori simulati partono da questi prezzi."
        )
    if policy_document is None:
        warnings.append("Nessuna policy salvata per questo scope: lo scenario mostra solo le metriche.")
    return warnings


def _run_one(
    snapshot: DoctorSnapshot,
    book: _Book,
    req: ScenarioInput,
    *,
    policy_document: Mapping[str, Any] | None,
    repo: Any,
    now: datetime,
    baseline: _State,
    meta: Mapping[str, Any],
) -> ScenarioResult:
    V = book.invested
    total_before = V + book.cash
    warnings = _base_warnings(snapshot, policy_document)
    common = {
        "label": req.label,
        "mode": req.mode,
        "scope": _scope(snapshot),
        "policy_id": meta.get("policy_id"),
        "policy_version": meta.get("policy_version"),
        "before": baseline.side(VOLATILITY_BEFORE_REASON),
        "total_before": total_before,
        "cash_in": float(req.new_cash),
        "methodology_version": METHODOLOGY_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "data_quality": DataQuality(**snapshot.data_quality),
        "calculated_at": now.isoformat(),
        "tax_model": req.tax_model,
        "disclaimer": SCENARIO_DISCLAIMER,
    }

    def infeasible(exc: _Infeasible, turnover: float | None = None) -> ScenarioResult:
        return ScenarioResult(
            **common, feasible=False, infeasible_code=exc.code, infeasible_reason=exc.reason,
            required_new_cash=exc.required_new_cash, warnings=warnings,
            costs=ScenarioCosts(fee_model=req.fee_model), turnover_pct=turnover,
        )

    try:
        if req.mode == "manual":
            plan = _plan_manual(book, req)
        elif req.mode == "new_cash_only":
            plan = _plan_new_cash(book, req, policy_document)
        else:
            plan = _plan_rebalance(book, req)
    except _Infeasible as exc:
        return infeasible(exc)

    values = {
        a: max(0.0, book.values[a] + plan.buys.get(a, 0.0) - plan.sells.get(a, 0.0)) for a in book.ids
    }
    cash_after = plan.cash_after
    if cash_after < 0:
        if cash_after < -0.005:
            return infeasible(_Infeasible("insufficient_cash", "La liquidità risulterebbe negativa."))
        cash_after = 0.0
    traded = sum(plan.buys.values()) + sum(plan.sells.values())
    turnover = traded / (2 * V) * 100.0 if V > MONEY_TOL else None
    limit = req.constraints.max_turnover_pct
    if limit is not None and turnover is not None and turnover > limit + WEIGHT_TOL:
        return infeasible(
            _Infeasible(
                "turnover_exceeded",
                f"Il turnover dello scenario ({format_it(turnover, 1)}%) supera il massimo indicato "
                f"({format_threshold_it(limit)}%).",
            ),
            turnover,
        )

    after_snapshot = _simulated_snapshot(snapshot, book, values, cash_after)
    after = _evaluate(after_snapshot, policy_document, repo, now, meta=meta, memo=book.memo)

    if req.constraints.keep_equity_total and not _same_metric(
        baseline.metrics["equity_weight_pct"], after.metrics["equity_weight_pct"],
    ):
        before_eq = baseline.metrics["equity_weight_pct"].value
        after_eq = after.metrics["equity_weight_pct"].value
        return infeasible(
            _Infeasible(
                "keep_equity_total",
                "Lo scenario cambia la quota azionaria "
                f"({format_it(before_eq or 0.0, 2)}% → {format_it(after_eq or 0.0, 2)}%) "
                "ma il vincolo «quota azionaria invariata» è attivo.",
            ),
            turnover,
        )

    changes = []
    for a in book.ids:
        h = book.by_id[a]
        before_w = book.values[a] / V * 100.0 if V > MONEY_TOL else 0.0
        after_inv = after_snapshot.invested_value
        after_w = values[a] / after_inv * 100.0 if after_inv > MONEY_TOL else 0.0
        delta = values[a] - book.values[a]
        changes.append(ScenarioChange(
            asset_id=a, symbol=h.symbol, name=h.name, isin=h.isin, asset_class=book.memo.policy_asset_class(h),
            action="buy" if delta > MONEY_TOL else ("sell" if delta < -MONEY_TOL else "hold"),
            before_value=book.values[a], after_value=values[a], delta_value=delta,
            before_weight=before_w, after_weight=after_w, delta_weight=after_w - before_w,
            fees=plan.fees.get(a, 0.0),
        ))
    if all(c.action == "hold" for c in changes):
        warnings.append("Lo scenario non modifica le posizioni.")
    warnings.extend(plan.warnings)
    resolved, new = _rule_changes(baseline.evaluation.results, after.evaluation.results)
    return ScenarioResult(
        **common,
        feasible=True,
        after=after.side(VOLATILITY_AFTER_REASON),
        changes=changes,
        warnings=warnings,
        violations_resolved=resolved,
        violations_new=new,
        required_new_cash=None,
        total_after=after_snapshot.invested_value + cash_after,
        costs=ScenarioCosts(
            total=plan.costs, variable=plan.variable_cost, fixed=plan.fixed_cost,
            operations=plan.operations, fee_model=req.fee_model,
        ),
        turnover_pct=turnover,
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def _canonical(snapshot: DoctorSnapshot) -> DoctorSnapshot:
    """Same snapshot with holdings in asset_id order.

    Float sums (invested value, metric denominators) then do not depend on the
    order the positions were loaded in, so an aggregate scope gives identical
    results for any permutation of its portfolio ids/positions. Same snapshot_id.
    """
    return snapshot_from_holdings(
        sorted(snapshot.holdings, key=lambda h: (int(h.asset_id), h.symbol)),
        portfolio_ids=snapshot.portfolio_ids,
        base_currency=snapshot.base_currency,
        cash_value=snapshot.cash_value,
        price_as_of=dict(snapshot.price_as_of),
        stale_asset_ids=set(snapshot.stale_asset_ids),
        missing_price_asset_ids=set(snapshot.missing_price_asset_ids),
        last_successful_price_sync=snapshot.last_successful_price_sync,
        last_sync_status=snapshot.last_sync_status,
        sync_available=snapshot.sync_available,
        freshness_note=snapshot.freshness_note,
    )


def _check_snapshot(snapshot: DoctorSnapshot, expected: str | None) -> None:
    if expected and expected != snapshot.snapshot_id:
        err = SnapshotChanged(
            "Il portafoglio è cambiato dall'ultima lettura: ricarica e ripeti la simulazione",
        )
        err.details["current_snapshot_id"] = snapshot.snapshot_id
        raise err


def _meta(policy_id: int | None, policy_version: int | None, policy_name: str | None) -> dict[str, Any]:
    return {"policy_id": policy_id, "policy_version": policy_version, "policy_name": policy_name}


def preview_scenario(
    snapshot: DoctorSnapshot,
    request: ScenarioInput | Mapping[str, Any],
    *,
    policy_document: Mapping[str, Any] | None,
    repo: Any = None,
    now: datetime | None = None,
    baseline_metrics: dict[str, Any] | None = None,
    policy_id: int | None = None,
    policy_version: int | None = None,
    policy_name: str | None = None,
) -> ScenarioResult:
    """Simulate one scenario on ``snapshot`` (pure, read-only).

    Raises InvalidRequest (400) for a malformed request or an asset not in
    the scope, SnapshotChanged (409) when ``request.snapshot_id`` is not the
    snapshot's id.
    """
    req = _as_input(request)
    _check_snapshot(snapshot, getattr(req, "snapshot_id", None))
    snapshot = _canonical(snapshot)
    current = _utc(now)
    meta = _meta(policy_id, policy_version, policy_name)
    book = _book(snapshot)
    baseline = _evaluate(snapshot, policy_document, repo, current, baseline_metrics, meta, memo=book.memo)
    return _run_one(
        snapshot, book, req, policy_document=policy_document, repo=repo, now=current,
        baseline=baseline, meta=meta,
    )


def _rank_key(index: int, r: ScenarioResult) -> tuple:
    if not r.feasible or r.after is None:
        return (1, 0, 0, 0, 0, 0.0, r.required_new_cash or 0.0, 0.0, index)
    s = r.after.evaluation_summary
    return (
        0, s.failed, s.unknown, -len(r.violations_resolved), len(r.violations_new),
        round(r.costs.total, 6), round(r.cash_in, 6), round(r.turnover_pct or 0.0, 6), index,
    )


def _explanation(results: Sequence[ScenarioResult], ranking: Sequence[ScenarioRankItem]) -> str:
    order = (
        "Ordinamento: regole violate dopo lo scenario, regole non verificabili, violazioni risolte, "
        "nuove violazioni, costi, nuova liquidità, turnover."
    )
    first = ranking[0] if ranking else None
    if first is None or not first.feasible:
        return "Nessuno scenario è realizzabile con i vincoli indicati. " + order
    name = results[first.index].label or f"Scenario {first.index + 1}"
    return (
        f"«{name}» è primo secondo le tue regole: {first.failed_after} regole violate dopo lo scenario, "
        f"{first.violations_resolved} violazioni risolte, costi {_money_it(first.costs)}, "
        f"nuova liquidità {_money_it(first.cash_in)}. " + order
    )


def compare_scenarios(
    snapshot: DoctorSnapshot,
    requests: Iterable[ScenarioInput | Mapping[str, Any]],
    *,
    policy_document: Mapping[str, Any] | None,
    repo: Any = None,
    now: datetime | None = None,
    expected_snapshot_id: str | None = None,
    baseline_metrics: dict[str, Any] | None = None,
    policy_id: int | None = None,
    policy_version: int | None = None,
    policy_name: str | None = None,
) -> ScenarioComparison:
    """2–3 scenarios on the *same* snapshot, plus the current state and a ranking."""
    inputs = [_as_input(r) for r in requests]
    if not 2 <= len(inputs) <= 3:
        raise InvalidRequest(
            "Servono da 2 a 3 scenari",
            field_errors=[{"field": "scenarios", "code": "invalid_length", "message": "Da 2 a 3 scenari"}],
        )
    _check_snapshot(snapshot, expected_snapshot_id)
    for req in inputs:
        _check_snapshot(snapshot, getattr(req, "snapshot_id", None))
    snapshot = _canonical(snapshot)
    current = _utc(now)
    meta = _meta(policy_id, policy_version, policy_name)
    book = _book(snapshot)
    baseline = _evaluate(snapshot, policy_document, repo, current, baseline_metrics, meta, memo=book.memo)
    results = [
        _run_one(snapshot, book, req, policy_document=policy_document, repo=repo, now=current, baseline=baseline, meta=meta)
        for req in inputs
    ]
    ordered = sorted(range(len(results)), key=lambda i: _rank_key(i, results[i]))
    ranking = []
    for rank, i in enumerate(ordered, start=1):
        r = results[i]
        summary = r.after.evaluation_summary if r.after is not None else None
        ranking.append(ScenarioRankItem(
            index=i, label=r.label, rank=rank, feasible=r.feasible,
            failed_after=summary.failed if summary else None,
            unknown_after=summary.unknown if summary else None,
            violations_resolved=len(r.violations_resolved), violations_new=len(r.violations_new),
            costs=r.costs.total, cash_in=r.cash_in, turnover_pct=r.turnover_pct,
        ))
    best = ranking[0].index if ranking and ranking[0].feasible else None
    return ScenarioComparison(
        scope=_scope(snapshot),
        policy_id=policy_id,
        policy_version=policy_version,
        snapshot_id=snapshot.snapshot_id,
        methodology_version=METHODOLOGY_VERSION,
        calculated_at=current.isoformat(),
        data_quality=DataQuality(**snapshot.data_quality),
        current=baseline.side(VOLATILITY_BEFORE_REASON),
        scenarios=results,
        ranking=ranking,
        best_index=best,
        explanation=_explanation(results, ranking),
        disclaimer=SCENARIO_DISCLAIMER,
    )
