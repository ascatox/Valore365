"""Read-only diagnostic export of the inputs behind TWR/MWR (TASK-PERF-02).

``build_performance_audit_export`` dumps, for one portfolio or an aggregate,
exactly the dated external flows and the end-of-day valuations that
``PerformanceService`` uses for TWR and MWR, together with the service's own
results, so an auditor can recompute both independently
(``scripts/audit/twr_mwr_offline_auditor.py``).

The export reuses the service internals — same lookup cache, same window
resolution (``_resolve_period_range`` / ``_resolve_date_range``), same cash
model fold (``_external_flows_from_history``) and the same
``_get_cashflows_with_fallback`` — so the flows exported are the flows the
service reads. Flows are rebuilt per portfolio to attribute them, and the
union is checked against the service list (``consistency_check``).

Read-only: only repository read methods are called, nothing is written.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .performance_service import IMPLICIT_CONTRIBUTION, PerformanceService

MAX_AUDIT_FLOWS = 500
VALUATION_METHOD = "end_of_day; flows on start day included in start value; ACT/365"
IMPLICIT_REASON = "cash_shortfall_end_of_day"
_AMOUNT_TOL = 1e-6


def _flow_key(cf: Any) -> tuple[str, str, float]:
    return (str(cf.date), str(cf.side), round(float(cf.amount), 6))


def _history_by_portfolio(
    perf: PerformanceService, ref: Any, scope: int | tuple[int, ...], user_id: str, end: date, cache: Any
) -> dict[int, list]:
    # Same cached read _get_cashflows_with_fallback folds: every cash-moving
    # transaction (trades included) up to `end`, from the first one.
    history = perf._cashflows(ref, user_id, None, end, True, cache)
    if isinstance(scope, tuple):
        return {pid: list(history.get(pid, []) or []) for pid in scope}
    return {scope: list(history or [])}


def _fx_missing(repo: Any, ids: list[int], user_id: str) -> tuple[list[str] | None, str | None]:
    """Currencies converted at 1.0 in the current cash fold, when the repo exposes it."""
    try:
        if len(ids) == 1:
            getter = getattr(repo, "get_current_cash_balance_detail", None)
            detail = getter(ids[0], user_id) if callable(getter) else None
        else:
            getter = getattr(repo, "get_current_cash_balance_detail_multi", None)
            detail = getter(ids, user_id) if callable(getter) else None
    except Exception:  # pragma: no cover - diagnostic only, never fails the export
        detail = None
    if detail is None:
        return None, "fx_missing non disponibile (dettaglio della liquidità non leggibile)."
    missing = getattr(detail, "fx_missing_currencies", None)
    if missing is None:
        return None, "fx_missing non disponibile (dettaglio della liquidità senza fx_missing_currencies)."
    return sorted(str(c) for c in missing), None


def build_performance_audit_export(
    perf_service: PerformanceService,
    portfolio_ids: list[int] | int,
    user_id: str,
    period: str = "1y",
    start_date: date | None = None,
    end_date: date | None = None,
    max_flows: int = MAX_AUDIT_FLOWS,
    offset: int = 0,
) -> dict[str, Any]:
    """Dated flows, valuations and service results of one TWR/MWR window (read-only).

    ``start_date``/``end_date`` select a custom window (``period`` is then
    reported as "custom"); otherwise ``period`` is resolved like
    ``get_performance_summary``. ``max_flows`` is capped at 500; ``offset``
    pages ``external_flows`` (must be >= 0). Every other list is complete.
    """
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset non valido: deve essere un intero >= 0")
    if isinstance(max_flows, bool) or not isinstance(max_flows, int) or max_flows < 1:
        raise ValueError("max_flows non valido: deve essere un intero >= 1")
    limit = min(max_flows, MAX_AUDIT_FLOWS)

    perf = perf_service
    ref: Any = portfolio_ids if isinstance(portfolio_ids, int) else list(portfolio_ids)
    scope = perf._scope_key(ref)
    ids = [scope] if isinstance(scope, int) else list(scope)
    resolve = getattr(perf.repo, "resolve_portfolio_scope", None)
    if callable(resolve):
        # Ownership (and same base currency) before any read, also for one id.
        resolve(list(ids), user_id)

    cache = perf._cache_for(ref, user_id)
    custom = start_date is not None or end_date is not None
    if custom:
        start, end = perf._resolve_date_range(ref, user_id, start_date, end_date, cache=cache)
        period_label = "custom"
    else:
        start, end = perf._resolve_period_range(ref, user_id, period, cache=cache)
        period_label = period

    # Exactly the flows TWR/MWR read.
    service_flows, implicit_only = perf._get_cashflows_with_fallback(ref, user_id, start, end, cache=cache)

    # Same fold, per portfolio, to know where each flow comes from.
    histories = _history_by_portfolio(perf, ref, scope, user_id, end, cache)
    attributed: list[tuple[int, Any]] = []
    for pid in ids:
        for cf in perf._external_flows_from_history(histories.get(pid, []), start, end):
            attributed.append((pid, cf))
    attributed.sort(key=lambda item: item[1].date)  # stable: per-portfolio order kept

    union_counter = Counter(_flow_key(cf) for _, cf in attributed)
    service_counter = Counter(_flow_key(cf) for cf in service_flows)
    union_total = sum(float(cf.amount) for _, cf in attributed)
    service_total = sum(float(cf.amount) for cf in service_flows)
    consistency_check = {
        "flows_match_service": union_counter == service_counter,
        "count_match": len(attributed) == len(service_flows),
        "totals_match": abs(union_total - service_total) <= _AMOUNT_TOL,
        "export_flow_count": len(attributed),
        "service_flow_count": len(service_flows),
        "export_total_amount_eur": round(union_total, 8),
        "service_total_amount_eur": round(service_total, 8),
        "service_implicit_only": bool(implicit_only),
    }

    all_flows: list[dict[str, Any]] = []
    for pid, cf in attributed:
        synthetic = cf.side == IMPLICIT_CONTRIBUTION
        row = {
            "date": cf.date,
            "amount_eur": float(cf.amount),
            "side": cf.side,
            "source": "cash_model" if synthetic else "transaction",
            "portfolio_id": pid,
            "synthetic_flow": synthetic,
            # A flow on the start day is already inside the start value.
            "in_twr_mwr": date.fromisoformat(cf.date) > start,
        }
        if synthetic:
            row["reason"] = IMPLICIT_REASON
        all_flows.append(row)

    page = all_flows[offset: offset + limit]

    net_by_date: dict[str, float] = {}
    for row in all_flows:
        net_by_date[row["date"]] = net_by_date.get(row["date"], 0.0) + row["amount_eur"]
    net_flows_by_date = [
        {
            "date": d,
            "amount_eur": round(amount, 8),
            "in_twr_mwr": date.fromisoformat(d) > start,
        }
        for d, amount in sorted(net_by_date.items())
    ]

    before_start = start - timedelta(days=1)
    flow_days = {date.fromisoformat(d) for d in net_by_date}
    # Same dates get_performance_summary reads: served by the shared cache.
    values = perf._values(ref, user_id, {before_start, start, end} | flow_days, cache)
    valuation_dates = sorted({start, end} | flow_days)
    valuation_on_flow_dates = [
        {"date": d.isoformat(), "value_eur": float(values[d]) if values.get(d) is not None else None}
        for d in valuation_dates
    ]

    # Service results on the same window and the same cache.
    if custom:
        twr = perf.calculate_twr(ref, user_id, start, end, cache=cache)
        mwr = perf.calculate_mwr(ref, user_id, start, end, cache=cache)
        service_results = {"source": "calculate_twr/calculate_mwr", "twr": twr.model_dump(), "mwr": mwr.model_dump()}
    else:
        summary = perf.get_performance_summary(ref, user_id, period)
        service_results = {
            "source": "get_performance_summary",
            "twr": summary.twr.model_dump(),
            "mwr": summary.mwr.model_dump(),
            "initial_value": summary.initial_value,
            "current_value": summary.current_value,
            "net_invested": summary.net_invested,
            "implicit_contributions": summary.implicit_contributions,
        }

    # Data quality: only what is cheaply known, nothing inferred.
    notes: list[str] = []
    fx_missing, fx_note = _fx_missing(perf.repo, ids, user_id)
    if fx_note:
        notes.append(fx_note)
    elif fx_missing:
        notes.append(
            "Valute senza cambio alla data di alcune transazioni (convertite a 1.0): "
            + ", ".join(fx_missing) + "."
        )
    prices_missing: list[str] = []
    cumulative = 0.0
    invested_before = float(values.get(before_start) or 0.0) > 0
    for d in valuation_dates:
        cumulative += net_by_date.get(d.isoformat(), 0.0)
        value = values.get(d)
        money_in = invested_before or cumulative > _AMOUNT_TOL
        if value is None or (float(value) <= 0 and money_in):
            prices_missing.append(d.isoformat())
    if prices_missing:
        notes.append(
            "Valore nullo o assente in date con capitale investito: probabili quotazioni mancanti "
            "(i rendimenti di quei sottoperiodi non sono affidabili)."
        )
    if not consistency_check["flows_match_service"]:
        notes.append("I flussi ricostruiti per portafoglio non coincidono con quelli del servizio.")

    return {
        "portfolio_ids": ids,
        "period": period_label,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "period_days": max((end - start).days, 1),
        "valuation_method": VALUATION_METHOD,
        "generated_at": datetime.now(UTC).isoformat(),
        "valuation_start": float(values[start]),
        "valuation_before_start": float(values[before_start]),
        "valuation_end": float(values[end]),
        "external_flows": page,
        "implicit_flows": [row for row in page if row["synthetic_flow"]],
        "total_implicit_flows": sum(1 for row in all_flows if row["synthetic_flow"]),
        "net_flows_by_date": net_flows_by_date,
        "valuation_on_flow_dates": valuation_on_flow_dates,
        "service_results": service_results,
        "consistency_check": consistency_check,
        "data_quality": {"fx_missing": fx_missing, "prices_missing": prices_missing, "notes": notes},
        "total_flows": len(all_flows),
        "offset": offset,
        "limit": limit,
        "truncated": offset + limit < len(all_flows),
    }
