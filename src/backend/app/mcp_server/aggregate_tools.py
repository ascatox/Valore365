"""Read-only MCP tools over several portfolios read as one (vista aggregata).

Every tool is named ``get_aggregate_*`` and takes ``portfolio_ids``: 2 to 20
distinct ids of portfolios owned by the authenticated user, all with the same
base currency. The existing single-portfolio tools keep their schema.

Each tool reuses the repository/service call of the matching app route in
``app/api/routes_aggregate.py`` (``*_multi`` repository methods, services
that accept a list of ids), so the numbers are the ones the app shows in its
aggregate view; the output format follows the matching single-portfolio
Copilot tool. Portfolios stay separate in storage: nothing is merged or
written.

Scope rules (shared with the app, see ``app.repository._scope``):
- every id is checked with ``resolve_portfolio_scope`` before any read; a
  missing or foreign id gives the same "Portfolio non trovato" error, with
  no data and no hint about which id failed;
- mixed base currencies give MIXED_CURRENCY_MESSAGE;
- duplicate ids are rejected by the input schema (``uniqueItems``), so the
  caller always knows exactly which portfolios were aggregated.

Not available in aggregate form (no aggregate implementation in the app):
target drift and rebalancing (targets are per portfolio), what-if, PAC,
dividends, costs, income projection, day movers, cash balance (included in
get_aggregate_summary).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..copilot_tools import _TOOL_HANDLERS as COPILOT_HANDLERS
from ..repository._scope import EMPTY_SCOPE_MESSAGE, MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE

MIN_AGGREGATE_PORTFOLIOS = 2
# Same cap as the app aggregate routes (routes_aggregate.MAX_AGGREGATE_PORTFOLIOS).
MAX_AGGREGATE_PORTFOLIOS = 20

AGGREGATE_NOTE = (
    "Vista aggregata in sola lettura: i portafogli restano separati e i valori sono "
    "calcolati come nella vista aggregata dell'app (stessa valuta base)."
)

# Scope errors whose fixed message is safe to return as is.
_SCOPE_MESSAGES = frozenset({EMPTY_SCOPE_MESSAGE, MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE})


@dataclass(frozen=True)
class AggregateTool:
    name: str
    title: str
    description: str
    # (deps, ids, user_id) -> result dict, ids already validated.
    handler: Callable[[Any, list[int], str], dict[str, Any]]
    heavy: bool = False


def portfolio_ids_schema(max_portfolio_id: int) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "integer", "minimum": 1, "maximum": max_portfolio_id},
        "minItems": MIN_AGGREGATE_PORTFOLIOS,
        "maxItems": MAX_AGGREGATE_PORTFOLIOS,
        "uniqueItems": True,
        "description": (
            f"Id dei portafogli da aggregare (da {MIN_AGGREGATE_PORTFOLIOS} a {MAX_AGGREGATE_PORTFOLIOS}, "
            "distinti, stessa valuta base; vedi list_portfolios)."
        ),
    }


def aggregate_input_schema(max_portfolio_id: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"portfolio_ids": portfolio_ids_schema(max_portfolio_id)},
        "required": ["portfolio_ids"],
        "additionalProperties": False,
    }


def scope_error_message(exc: ValueError) -> str:
    """Message of a scope error; anything else reads as "not found"."""
    message = str(exc)
    return message if message in _SCOPE_MESSAGES else NOT_FOUND_MESSAGE


# --- handlers -------------------------------------------------------------


def _summary(deps: Any, ids: list[int], user_id: str) -> dict[str, Any]:
    # Same call as GET /portfolios/aggregate/summary.
    s = deps.repo.get_summary_multi(ids, user_id)
    return {
        "market_value": round(s.market_value, 2),
        "cost_basis": round(s.cost_basis, 2),
        "unrealized_pl": round(s.unrealized_pl, 2),
        "unrealized_pl_pct": round(s.unrealized_pl_pct, 2),
        "day_change": round(s.day_change, 2),
        "day_change_pct": round(s.day_change_pct, 2),
        "cash_balance": round(s.cash_balance, 2),
    }


def _positions(deps: Any, ids: list[int], user_id: str) -> dict[str, Any]:
    # Same call as GET /portfolios/aggregate/positions: one row per asset.
    positions = deps.repo.get_positions_multi(ids, user_id)
    top = sorted(positions, key=lambda p: p.weight, reverse=True)[:30]
    return {
        "positions_count": len(positions),
        "positions": [
            {
                "symbol": p.symbol,
                "name": p.name,
                "weight": round(p.weight, 2),
                "market_value": round(p.market_value, 2),
                "cost_basis": round(p.avg_cost * p.quantity, 2) if p.avg_cost else 0,
                "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
                "day_change_pct": round(p.day_change_pct, 2) if p.day_change_pct else 0,
                "quantity": float(p.quantity),
                "market_price": round(p.market_price, 4) if p.market_price else 0,
            }
            for p in top
        ],
    }


def _allocation(deps: Any, ids: list[int], user_id: str) -> dict[str, Any]:
    # Same call as GET /portfolios/aggregate/allocation.
    allocation = deps.repo.get_allocation_multi(ids, user_id)
    return {
        "allocation": [
            {
                "symbol": a.symbol,
                "market_value": round(a.market_value, 2),
                "weight_pct": round(a.weight_pct, 2),
            }
            for a in allocation
        ],
    }


def _recent_transactions(deps: Any, ids: list[int], user_id: str) -> dict[str, Any]:
    # Same call as GET /portfolios/aggregate/transactions (newest first).
    txns = deps.repo.list_transactions_multi(ids, user_id)[:20]
    return {
        "transactions": [
            {
                "id": t.id,
                "portfolio_id": t.portfolio_id,
                "portfolio_name": t.portfolio_name or "",
                "date": t.trade_at.isoformat() if t.trade_at else None,
                "type": t.side,
                "symbol": t.symbol or "CASH",
                "asset_name": t.asset_name or "",
                "quantity": float(t.quantity),
                "price": float(t.price),
                "total": round(float(t.quantity) * float(t.price), 2),
                "currency": t.trade_currency,
                "fees": float(t.fees) if t.fees else 0,
            }
            for t in txns
        ],
    }


def _copilot(name: str) -> Callable[[Any, list[int], str], dict[str, Any]]:
    """Run a Copilot handler whose services accept a list of ids (PortfolioRef).

    performance_service.get_performance_summary, run_monte_carlo_projection,
    analyze_portfolio_health, run_stress_test and compute_portfolio_xray are
    the functions the aggregate routes call with the same list.
    """

    def handler(deps: Any, ids: list[int], user_id: str) -> dict[str, Any]:
        return COPILOT_HANDLERS[name](
            {}, deps.repo, deps.performance_service, list(ids), user_id,
            finance_client=deps.finance_client,
            # Read-only: no justETF client, so X-Ray never writes etf_enrichment.
            justetf_client=None,
        )

    return handler


AGGREGATE_TOOLS: dict[str, AggregateTool] = {
    tool.name: tool
    for tool in (
        AggregateTool(
            name="get_aggregate_summary",
            title="Riepilogo aggregato",
            description=(
                "Riepilogo complessivo di più portafogli letti come uno solo: valore di mercato, costo, "
                "P&L, variazione giornaliera e cash, sommati come nella vista aggregata dell'app."
            ),
            handler=_summary,
        ),
        AggregateTool(
            name="get_aggregate_positions",
            title="Posizioni aggregate",
            description=(
                "Posizioni di più portafogli unite per titolo (quantità e costi sommati, pesi ricalcolati "
                "sul totale). Massimo 30 posizioni ordinate per peso."
            ),
            handler=_positions,
        ),
        AggregateTool(
            name="get_aggregate_allocation",
            title="Allocazione aggregata",
            description="Allocazione per titolo di più portafogli letti come uno solo (pesi sul totale).",
            handler=_allocation,
        ),
        AggregateTool(
            name="get_aggregate_performance",
            title="Performance aggregata",
            description=(
                "Performance TWR di più portafogli letti come uno solo (1 mese, 3 mesi, YTD, 1 anno), "
                "calcolata sui valori e flussi combinati come nell'app, non come media dei singoli."
            ),
            handler=_copilot("get_performance"),
            heavy=True,
        ),
        AggregateTool(
            name="get_aggregate_recent_transactions",
            title="Transazioni recenti aggregate",
            description=(
                "Ultime 20 transazioni di più portafogli, dalla più recente, con portfolio_id e nome "
                "del portafoglio di ogni riga."
            ),
            handler=_recent_transactions,
        ),
        AggregateTool(
            name="get_aggregate_health",
            title="Salute aggregata",
            description=(
                "Punteggio di salute (0-100), rischio, diversificazione, alert e suggerimenti di più "
                "portafogli letti come uno solo, come nel Portfolio Doctor aggregato dell'app."
            ),
            handler=_copilot("get_portfolio_health"),
            heavy=True,
        ),
        AggregateTool(
            name="get_aggregate_monte_carlo",
            title="Monte Carlo aggregato",
            description=(
                "Proiezioni Monte Carlo (anni 1-10, percentili P25/P50/P75 come indice base 100) di più "
                "portafogli letti come uno solo."
            ),
            handler=_copilot("get_monte_carlo"),
            heavy=True,
        ),
        AggregateTool(
            name="get_aggregate_stress_test",
            title="Stress test aggregato",
            description="Scenari storici e di shock applicati a più portafogli letti come uno solo.",
            handler=_copilot("get_stress_test"),
            heavy=True,
        ),
        AggregateTool(
            name="get_aggregate_xray",
            title="X-Ray aggregato",
            description=(
                "X-Ray di più portafogli letti come uno solo: principali titoli sottostanti degli ETF, "
                "esposizione geografica e settoriale (solo dati ETF già in cache)."
            ),
            handler=_copilot("get_xray_summary"),
            heavy=True,
        ),
    )
}

AGGREGATE_HEAVY_TOOLS: frozenset[str] = frozenset(name for name, t in AGGREGATE_TOOLS.items() if t.heavy)
