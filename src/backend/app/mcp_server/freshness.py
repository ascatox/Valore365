"""Freschezza dei dati nelle risposte MCP (TASK-54).

``data_freshness_block`` è aggiunto (una volta, qui) a ogni tool di
FRESHNESS_TOOLS: ultima sincronizzazione riuscita dei prezzi, esito
dell'ultima run, simboli con prezzo fermo e prezzo più vecchio fra le
posizioni. ``get_data_freshness`` è il tool dedicato: per posizione ultimo
tick, ultima barra giornaliera, flag e motivo del prezzo fermo, più lo stato
globale della sincronizzazione. Sola lettura: nessuna scrittura, nessuna
chiamata al provider; le posizioni vengono dal calcolo già fatto dal tool
(memoize_positions) o da una lettura del repository.

Ogni lettura fallita degrada in valori null con una nota: la freschezza non
deve mai far fallire il tool che la accompagna.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger("valore365.mcp")

DATA_FRESHNESS_TOOL = "get_data_freshness"

# Tools whose output carries portfolio values: their result gets data_freshness.
FRESHNESS_TOOLS: frozenset[str] = frozenset({
    "get_portfolio_summary",
    "get_positions",
    "get_target_drift",
    "get_performance",
    "get_portfolio_health",
    "get_day_movers",
    "calculate_rebalance_orders",
    "calculate_what_if",
    "get_stress_test",
    "get_aggregate_summary",
    "get_aggregate_positions",
    "get_aggregate_allocation",
    "get_aggregate_performance",
    "get_aggregate_health",
    "get_aggregate_stress_test",
    "get_aggregate_performance_audit",
    # Portfolio Doctor 2.0: metric/evaluation/scenario values depend on prices.
    "read_doctor_metrics",
    "read_doctor_violations",
    "build_doctor_scenario",
    "compare_doctor_scenarios",
})

SYNC_UNAVAILABLE_NOTE = "Stato della sincronizzazione dei prezzi non disponibile."
MAX_SYMBOLS = 50


def _iso(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None


def _sort_key(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    return None


def sync_status(repo: Any) -> dict[str, Any]:
    """Global sync state: last success, last run status/finish, running flag (None when unknown)."""
    out: dict[str, Any] = {
        "last_successful_price_sync": None,
        "last_sync_status": None,
        "last_sync_finished_at": None,
        "sync_running": None,
        "available": False,
    }
    getter = getattr(repo, "get_market_data_sync_overview", None)
    if getter is None:
        return out
    try:
        overview = getter()
    except Exception as exc:
        logger.debug("data_freshness: sync overview unavailable: %s", exc)
        return out
    if not isinstance(overview, dict):
        return out
    last_success = overview.get("last_success") if isinstance(overview.get("last_success"), dict) else {}
    last_run = overview.get("last_run") if isinstance(overview.get("last_run"), dict) else {}
    status = last_run.get("status")
    out.update(
        last_successful_price_sync=_iso(last_success.get("finished_at")),
        last_sync_status=status if isinstance(status, str) else None,
        last_sync_finished_at=_iso(last_run.get("finished_at")),
        sync_running=isinstance(overview.get("running"), dict),
        available=True,
    )
    return out


def _positions(repo: Any, portfolio_ids: list[int], user_id: str) -> list[Any] | None:
    try:
        if len(portfolio_ids) == 1:
            positions = repo.get_positions(portfolio_ids[0], user_id)
        else:
            positions = repo.get_positions_multi(portfolio_ids, user_id)
    except Exception as exc:
        logger.debug("data_freshness: positions unavailable: %s", exc)
        return None
    if not isinstance(positions, list):
        return None
    return [p for p in positions if float(getattr(p, "quantity", 0) or 0) > 0]


def _latest_price_value(p: Any) -> Any:
    """The newer of the latest tick and the daily close date of a position."""
    tick, bar = getattr(p, "last_price_at", None), getattr(p, "price_date", None)
    candidates = [v for v in (tick, bar) if _sort_key(v) is not None]
    return max(candidates, key=_sort_key) if candidates else None


def _note(sync: dict[str, Any], stale: list[str] | None, missing: list[str]) -> str:
    parts = []
    if not sync["available"]:
        parts.append(SYNC_UNAVAILABLE_NOTE)
    elif sync["last_successful_price_sync"] is None:
        parts.append("Nessuna sincronizzazione dei prezzi completata con successo finora.")
    elif sync["last_sync_status"] in ("partial", "failed"):
        parts.append(
            f"L'ultima sincronizzazione dei prezzi è {'parziale' if sync['last_sync_status'] == 'partial' else 'fallita'}: "
            "i valori usano gli ultimi prezzi disponibili."
        )
    if stale:
        parts.append(
            "Prezzo fermo per " + ", ".join(stale[:MAX_SYMBOLS])
            + " (nessuna chiusura per le ultime sedute della borsa dell'asset)."
        )
    if missing:
        parts.append("Nessun prezzo di mercato per " + ", ".join(missing[:MAX_SYMBOLS]) + ".")
    if stale is None:
        parts.append("Freschezza delle singole posizioni non disponibile.")
    if not parts:
        parts.append("Prezzi aggiornati all'ultima seduta conclusa della borsa di ogni posizione.")
    return " ".join(parts)


def data_freshness_block(repo: Any, portfolio_ids: list[int], user_id: str) -> dict[str, Any]:
    sync = sync_status(repo)
    positions = _positions(repo, portfolio_ids, user_id)
    stale: list[str] | None = None
    missing: list[str] = []
    oldest = None
    if positions is not None:
        stale = sorted({str(p.symbol) for p in positions if getattr(p, "price_stale", False)})
        values = []
        for p in positions:
            value = _latest_price_value(p)
            if value is None:
                missing.append(str(p.symbol))
            else:
                values.append(value)
        oldest = min(values, key=_sort_key) if values else None
    return {
        "last_successful_price_sync": sync["last_successful_price_sync"],
        "last_sync_status": sync["last_sync_status"],
        "last_sync_finished_at": sync["last_sync_finished_at"],
        "stale_symbols": stale[:MAX_SYMBOLS] if stale is not None else None,
        "oldest_price_at": _iso(oldest),
        "note": _note(sync, stale, sorted(set(missing))),
    }


def get_data_freshness(repo: Any, portfolio_id: int, user_id: str) -> dict[str, Any]:
    """Per-position freshness plus the global sync status (get_data_freshness tool)."""
    sync = sync_status(repo)
    positions = _positions(repo, [portfolio_id], user_id)
    asset_state: dict[int, dict] = {}
    getter = getattr(repo, "get_market_data_asset_sync", None)
    if positions and getter is not None:
        try:
            state = getter([int(p.asset_id) for p in positions])
            asset_state = state if isinstance(state, dict) else {}
        except Exception as exc:
            logger.debug("data_freshness: asset sync state unavailable: %s", exc)
    rows = []
    for p in sorted(positions or [], key=lambda x: str(x.symbol)):
        stale = bool(getattr(p, "price_stale", False))
        reason = getattr(p, "stale_reason", None)
        if _latest_price_value(p) is None and not reason:
            reason = "nessuna quotazione disponibile"
        state = asset_state.get(int(p.asset_id)) or {}
        rows.append({
            "symbol": p.symbol,
            "last_price_at": _iso(getattr(p, "last_price_at", None)),
            "last_bar_date": _iso(getattr(p, "price_date", None)),
            "stale": stale,
            "stale_reason": reason if (stale or reason) else None,
            "last_sync_success_at": _iso(state.get("last_success_at")),
            "last_sync_error": state.get("last_error") if isinstance(state.get("last_error"), str) else None,
        })
    stale_symbols = [r["symbol"] for r in rows if r["stale"]] if positions is not None else None
    missing = [r["symbol"] for r in rows if r["last_price_at"] is None and r["last_bar_date"] is None]
    return {
        "sync": {k: v for k, v in sync.items() if k != "available"},
        "positions_count": len(rows),
        "positions": rows,
        "stale_symbols": stale_symbols,
        "note": _note(sync, stale_symbols, missing),
    }
