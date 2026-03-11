"""Copilot Fase 2 — Tool definitions, executor, and computation logic.

Read-only tools that let the LLM agent fetch portfolio data on demand
and run server-side calculations (rebalance, what-if, PAC).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .performance_service import PerformanceService
from .repository import PortfolioRepository
from .services.portfolio_doctor import analyze_portfolio_health, run_monte_carlo_projection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (provider-agnostic)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # --- T1: Portfolio summary ---
    {
        "name": "get_portfolio_summary",
        "description": (
            "Ottieni il riepilogo del portafoglio: valore di mercato, costo, "
            "P&L, variazione giornaliera, cash disponibile e valuta base."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T2: Positions ---
    {
        "name": "get_positions",
        "description": (
            "Ottieni la lista delle posizioni attuali del portafoglio con "
            "peso percentuale, valore di mercato, costo, P&L e variazione giornaliera. "
            "Massimo 30 posizioni ordinate per peso."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T3: Target drift ---
    {
        "name": "get_target_drift",
        "description": (
            "Ottieni lo scostamento (drift) di ogni posizione rispetto al peso "
            "target configurato. Utile per capire se il portafoglio e' allineato "
            "al piano o serve ribilanciare."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T4: Performance ---
    {
        "name": "get_performance",
        "description": (
            "Ottieni la performance del portafoglio (TWR) per diversi periodi: "
            "1 mese, 3 mesi, da inizio anno (YTD) e 1 anno."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T5: Cash balance ---
    {
        "name": "get_cash_balance",
        "description": (
            "Ottieni il saldo cash disponibile nel portafoglio, "
            "con la valuta base."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T6: Recent transactions ---
    {
        "name": "get_recent_transactions",
        "description": (
            "Ottieni le ultime transazioni del portafoglio (massimo 20). "
            "Mostra data, tipo (buy/sell/deposit/withdrawal), simbolo, "
            "quantita', prezzo e importo totale."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T7: Portfolio health ---
    {
        "name": "get_portfolio_health",
        "description": (
            "Ottieni il punteggio di salute del portafoglio (0-100), "
            "il livello di rischio, la diversificazione, gli alert attivi "
            "e i suggerimenti di miglioramento."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T8: Day movers ---
    {
        "name": "get_day_movers",
        "description": (
            "Ottieni il miglior e peggior performer della giornata "
            "nel portafoglio, con la variazione percentuale."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T9: Monte Carlo ---
    {
        "name": "get_monte_carlo",
        "description": (
            "Ottieni le proiezioni Monte Carlo del portafoglio a 1-10 anni. "
            "Include rendimento medio annualizzato, volatilita' e "
            "percentili (P25, P50, P75) per ogni anno."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T10: Rebalance orders ---
    {
        "name": "calculate_rebalance_orders",
        "description": (
            "Calcola gli ordini di acquisto/vendita necessari per riallineare "
            "il portafoglio al target. Usa questo tool quando l'utente chiede "
            "come ribilanciare o tornare in target."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "available_cash": {
                    "type": "number",
                    "description": (
                        "Cash aggiuntivo da investire in EUR (opzionale). "
                        "Se omesso, usa il cash disponibile nel portafoglio."
                    ),
                },
            },
            "required": [],
        },
    },
    # --- T11: What-if ---
    {
        "name": "calculate_what_if",
        "description": (
            "Simula l'effetto di un'operazione (acquisto o vendita) sui pesi "
            "e la diversificazione del portafoglio. Utile per rispondere a "
            "'cosa succede se compro/vendo X?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["buy", "sell"],
                    "description": "Tipo di operazione: acquisto o vendita",
                },
                "symbol": {
                    "type": "string",
                    "description": "Simbolo dell'asset (es. VWCE.DE)",
                },
                "amount_eur": {
                    "type": "number",
                    "description": "Importo in EUR dell'operazione",
                },
            },
            "required": ["action", "symbol", "amount_eur"],
        },
    },
    # --- T12: PAC contribution ---
    {
        "name": "calculate_pac_contribution",
        "description": (
            "Calcola come distribuire un versamento periodico (PAC) mensile "
            "tra gli asset del portafoglio per avvicinarsi al target. "
            "Prioritizza le posizioni piu' sotto-pesate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "monthly_amount": {
                    "type": "number",
                    "description": "Importo mensile da investire in EUR",
                },
            },
            "required": ["monthly_amount"],
        },
    },
    # --- T13: Asset info ---
    {
        "name": "search_asset_info",
        "description": (
            "Cerca informazioni su un asset per simbolo. "
            "Restituisce nome, tipo, valuta, ultimo prezzo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Simbolo dell'asset (es. VWCE.DE, IWDA.AS)",
                },
            },
            "required": ["symbol"],
        },
    },
]


# ---------------------------------------------------------------------------
# Provider format conversion
# ---------------------------------------------------------------------------

def format_tools_for_provider(provider: str) -> list[dict]:
    """Convert TOOL_DEFINITIONS to provider-specific format."""
    if provider == "anthropic":
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in TOOL_DEFINITIONS
        ]
    # OpenAI, Gemini, OpenRouter, local all use OpenAI format
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOL_DEFINITIONS
    ]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def execute_tool(
    tool_name: str,
    tool_args: dict,
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> dict:
    """Execute a tool by name and return a JSON-serializable dict."""
    try:
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {"error": f"Tool sconosciuto: {tool_name}"}
        return handler(tool_args, repo, perf_service, portfolio_id, user_id)
    except Exception as exc:
        logger.exception("Tool execution error: %s", tool_name)
        return {"error": f"Errore nell'esecuzione del tool {tool_name}: {str(exc)}"}


# ---------------------------------------------------------------------------
# T1-T9: Informational tool handlers
# ---------------------------------------------------------------------------

def _get_portfolio_summary(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    summary = repo.get_summary(portfolio_id, user_id)
    return {
        "market_value": round(summary.market_value, 2),
        "cost_basis": round(summary.cost_basis, 2),
        "unrealized_pl": round(summary.unrealized_pl, 2),
        "unrealized_pl_pct": round(summary.unrealized_pl_pct, 2),
        "day_change": round(summary.day_change, 2),
        "day_change_pct": round(summary.day_change_pct, 2),
        "cash_balance": round(summary.cash_balance, 2),
        "base_currency": summary.base_currency,
    }


def _get_positions(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    positions = repo.get_positions(portfolio_id, user_id)
    sorted_pos = sorted(positions, key=lambda p: p.weight, reverse=True)[:30]
    return {
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
            for p in sorted_pos
        ],
    }


def _get_target_drift(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    allocation = repo.get_allocation(portfolio_id, user_id)
    alloc_map = {a.asset_id: a.weight_pct for a in allocation}

    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    except Exception:
        return {"drift": [], "note": "Nessun target configurato per questo portafoglio."}

    if not target_alloc:
        return {"drift": [], "note": "Nessun target configurato per questo portafoglio."}

    positions = repo.get_positions(portfolio_id, user_id)
    pos_map = {p.symbol: p for p in positions}

    drift_list = []
    for ta in target_alloc:
        current = alloc_map.get(ta.asset_id, 0.0)
        pos = pos_map.get(ta.symbol)
        drift_list.append({
            "symbol": ta.symbol,
            "name": ta.name if hasattr(ta, "name") else ta.symbol,
            "current_weight": round(current, 2),
            "target_weight": round(ta.weight_pct, 2),
            "drift": round(current - ta.weight_pct, 2),
            "market_value": round(pos.market_value, 2) if pos else 0,
        })

    return {"drift": drift_list}


def _get_performance(
    _args: dict, _repo: PortfolioRepository, perf_service: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    result = {}
    for period in ("1m", "3m", "ytd", "1y"):
        try:
            ps = perf_service.get_performance_summary(portfolio_id, user_id, period)
            result[f"twr_{period}"] = round(ps.twr.twr_pct, 2) if ps.twr.twr_pct is not None else None
        except Exception:
            result[f"twr_{period}"] = None
    return result


def _get_cash_balance(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    summary = repo.get_summary(portfolio_id, user_id)
    return {
        "total_cash": round(summary.cash_balance, 2),
        "base_currency": summary.base_currency,
    }


def _get_recent_transactions(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    txns = repo.list_transactions(portfolio_id, user_id)[:20]
    return {
        "transactions": [
            {
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


def _get_portfolio_health(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    doctor = analyze_portfolio_health(repo, portfolio_id, user_id)
    return {
        "score": doctor.score,
        "risk_level": doctor.summary.risk_level,
        "diversification": doctor.summary.diversification,
        "overlap": doctor.summary.overlap,
        "cost_efficiency": doctor.summary.cost_efficiency,
        "max_position_weight": round(doctor.metrics.max_position_weight, 2),
        "portfolio_volatility": (
            round(doctor.metrics.portfolio_volatility, 2)
            if doctor.metrics.portfolio_volatility is not None else None
        ),
        "weighted_ter": (
            round(doctor.metrics.weighted_ter, 2)
            if doctor.metrics.weighted_ter is not None else None
        ),
        "alerts": [
            {"severity": a.severity, "message": a.message}
            for a in doctor.alerts[:8]
        ],
        "suggestions": [
            {"priority": s.priority, "message": s.message}
            for s in doctor.suggestions[:5]
        ],
    }


def _get_day_movers(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    try:
        target_perf = repo.get_portfolio_target_performance(portfolio_id, user_id)
        best = (
            {"symbol": target_perf.best.symbol, "day_change_pct": target_perf.best.day_change_pct}
            if target_perf.best else None
        )
        worst = (
            {"symbol": target_perf.worst.symbol, "day_change_pct": target_perf.worst.day_change_pct}
            if target_perf.worst else None
        )
    except Exception:
        # Fallback: compute from positions
        positions = repo.get_positions(portfolio_id, user_id)
        if not positions:
            return {"best": None, "worst": None}
        sorted_by_day = sorted(
            [p for p in positions if p.day_change_pct is not None],
            key=lambda p: p.day_change_pct,
        )
        best = (
            {"symbol": sorted_by_day[-1].symbol, "day_change_pct": round(sorted_by_day[-1].day_change_pct, 2)}
            if sorted_by_day else None
        )
        worst = (
            {"symbol": sorted_by_day[0].symbol, "day_change_pct": round(sorted_by_day[0].day_change_pct, 2)}
            if sorted_by_day else None
        )

    return {"best": best, "worst": worst}


def _get_monte_carlo(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    mc = run_monte_carlo_projection(repo, portfolio_id, user_id)
    return {
        "annualized_mean_return_pct": round(mc.annualized_mean_return_pct, 2),
        "annualized_volatility_pct": round(mc.annualized_volatility_pct, 2),
        "projections": [
            {"year": p.year, "p25": p.p25, "p50": p.p50, "p75": p.p75}
            for p in mc.projections[:10]
            if p.year > 0
        ],
    }


# ---------------------------------------------------------------------------
# T10-T12: Computation tool handlers
# ---------------------------------------------------------------------------

def _calculate_rebalance_orders(
    args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    """T10: Calculate buy/sell orders to realign portfolio to target."""
    summary = repo.get_summary(portfolio_id, user_id)
    positions = repo.get_positions(portfolio_id, user_id)
    allocation = repo.get_allocation(portfolio_id, user_id)
    alloc_map = {a.asset_id: a.weight_pct for a in allocation}

    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    except Exception:
        return {"orders": [], "note": "Nessun target configurato."}

    if not target_alloc:
        return {"orders": [], "note": "Nessun target configurato."}

    pos_map = {p.symbol: p for p in positions}
    available_cash = args.get("available_cash", summary.cash_balance)
    if available_cash is None or available_cash < 0:
        available_cash = summary.cash_balance

    total_value = summary.market_value + available_cash
    orders = []

    for ta in target_alloc:
        current_w = alloc_map.get(ta.asset_id, 0.0)
        drift = current_w - ta.weight_pct
        pos = pos_map.get(ta.symbol)
        price = pos.market_price if pos and pos.market_price else None

        if abs(drift) < 0.5:
            continue  # within tolerance

        if drift < 0:
            # Under-weight -> buy
            amount = abs(drift) / 100.0 * total_value
            amount = min(amount, available_cash)
            if amount < 1:
                continue
            available_cash -= amount
            orders.append({
                "symbol": ta.symbol,
                "action": "buy",
                "amount_eur": round(amount, 2),
                "shares_approx": round(amount / price, 4) if price and price > 0 else None,
                "reason": f"Sotto-pesato di {abs(drift):.1f}pp rispetto al target ({ta.weight_pct:.1f}%)",
            })
        else:
            # Over-weight -> sell
            current_value = pos.market_value if pos else 0
            amount = drift / 100.0 * current_value
            if amount < 1:
                continue
            orders.append({
                "symbol": ta.symbol,
                "action": "sell",
                "amount_eur": round(amount, 2),
                "shares_approx": round(amount / price, 4) if price and price > 0 else None,
                "reason": f"Sovra-pesato di {drift:.1f}pp rispetto al target ({ta.weight_pct:.1f}%)",
            })

    # Sort by absolute drift (largest deviation first)
    orders.sort(key=lambda o: o["amount_eur"], reverse=True)

    return {
        "orders": orders,
        "total_value": round(total_value, 2),
        "cash_used": round(summary.cash_balance + (args.get("available_cash", 0) or 0) - available_cash, 2),
        "cash_remaining": round(available_cash, 2),
    }


def _calculate_what_if(
    args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    """T11: Simulate buy/sell impact on portfolio weights."""
    action = args.get("action", "buy")
    symbol = args.get("symbol", "")
    amount_eur = args.get("amount_eur", 0)

    if not symbol or amount_eur <= 0:
        return {"error": "Parametri mancanti: servono action, symbol e amount_eur > 0"}

    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    total_value = summary.market_value

    # Find the position
    pos = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    old_value = pos.market_value if pos else 0
    old_weight = pos.weight if pos else 0

    if action == "buy":
        new_value = old_value + amount_eur
        new_total = total_value + amount_eur
    else:  # sell
        if amount_eur > old_value:
            return {"error": f"Importo vendita ({amount_eur} EUR) superiore al valore della posizione ({round(old_value, 2)} EUR)"}
        new_value = old_value - amount_eur
        new_total = total_value - amount_eur

    new_weight = (new_value / new_total * 100) if new_total > 0 else 0

    # Check drift from target
    old_drift = None
    new_drift = None
    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
        allocation = repo.get_allocation(portfolio_id, user_id)
        alloc_map = {a.asset_id: a.weight_pct for a in allocation}
        for ta in target_alloc:
            if ta.symbol.upper() == symbol.upper():
                old_drift = round(old_weight - ta.weight_pct, 2)
                new_drift = round(new_weight - ta.weight_pct, 2)
                break
    except Exception:
        pass

    # Max position weight (concentration check)
    weights_after = []
    for p in positions:
        if p.symbol.upper() == symbol.upper():
            weights_after.append(new_weight)
        else:
            w = (p.market_value / new_total * 100) if new_total > 0 else 0
            weights_after.append(w)
    if not pos and action == "buy":
        weights_after.append(new_weight)

    max_weight_before = max((p.weight for p in positions), default=0)
    max_weight_after = max(weights_after, default=0)

    return {
        "symbol": symbol,
        "action": action,
        "amount_eur": amount_eur,
        "old_weight": round(old_weight, 2),
        "new_weight": round(new_weight, 2),
        "old_drift": old_drift,
        "new_drift": new_drift,
        "max_position_weight_before": round(max_weight_before, 2),
        "max_position_weight_after": round(max_weight_after, 2),
        "impact_on_concentration": (
            "migliora" if max_weight_after < max_weight_before
            else "peggiora" if max_weight_after > max_weight_before
            else "invariata"
        ),
    }


def _calculate_pac_contribution(
    args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str,
) -> dict:
    """T12: Distribute a monthly PAC amount across assets to approach target."""
    monthly_amount = args.get("monthly_amount", 0)
    if monthly_amount <= 0:
        return {"error": "Importo mensile deve essere > 0"}

    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    allocation = repo.get_allocation(portfolio_id, user_id)
    alloc_map = {a.asset_id: a.weight_pct for a in allocation}

    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    except Exception:
        return {"distribution": [], "note": "Nessun target configurato."}

    if not target_alloc:
        return {"distribution": [], "note": "Nessun target configurato."}

    pos_map = {p.symbol: p for p in positions}
    total_value = summary.market_value

    # Calculate drift for each target asset (negative drift = under-weight)
    assets_with_drift = []
    for ta in target_alloc:
        current_w = alloc_map.get(ta.asset_id, 0.0)
        drift = current_w - ta.weight_pct  # negative means under-weight
        pos = pos_map.get(ta.symbol)
        assets_with_drift.append({
            "symbol": ta.symbol,
            "target_weight": ta.weight_pct,
            "current_weight": current_w,
            "drift": drift,
            "price": pos.market_price if pos and pos.market_price else None,
        })

    # Sort: most under-weight first
    assets_with_drift.sort(key=lambda a: a["drift"])

    # Distribute: proportional to negative drift, capped
    total_negative_drift = sum(abs(a["drift"]) for a in assets_with_drift if a["drift"] < 0)
    remaining = monthly_amount
    distribution = []

    new_total = total_value + monthly_amount

    for asset in assets_with_drift:
        if remaining <= 0:
            break
        if asset["drift"] >= 0:
            # Already at or above target, skip
            continue
        # Allocate proportionally to drift
        if total_negative_drift > 0:
            share = abs(asset["drift"]) / total_negative_drift
        else:
            share = 1.0 / len(assets_with_drift)
        amount = min(round(share * monthly_amount, 2), remaining)
        remaining -= amount

        pos = pos_map.get(asset["symbol"])
        old_value = pos.market_value if pos else 0
        new_value = old_value + amount
        new_weight = (new_value / new_total * 100) if new_total > 0 else 0

        distribution.append({
            "symbol": asset["symbol"],
            "amount_eur": round(amount, 2),
            "shares_approx": (
                round(amount / asset["price"], 4)
                if asset["price"] and asset["price"] > 0 else None
            ),
            "current_weight": round(asset["current_weight"], 2),
            "target_weight": round(asset["target_weight"], 2),
            "new_weight_after": round(new_weight, 2),
        })

    # If there's remaining cash (all at target), distribute proportionally to targets
    if remaining > 0.01 and target_alloc:
        for d in distribution:
            bonus = remaining * (d["target_weight"] / 100)
            d["amount_eur"] = round(d["amount_eur"] + bonus, 2)
        remaining = 0

    return {
        "monthly_amount": monthly_amount,
        "distribution": distribution,
        "total_allocated": round(monthly_amount - remaining, 2),
    }


def _search_asset_info(
    args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    _portfolio_id: int, _user_id: str,
) -> dict:
    """T13: Search asset info by symbol."""
    symbol = args.get("symbol", "")
    if not symbol:
        return {"error": "Simbolo mancante"}

    asset = repo.get_asset_by_symbol(symbol)
    if not asset:
        return {"error": f"Asset non trovato per il simbolo: {symbol}"}

    result = {
        "symbol": asset["symbol"],
        "name": asset["name"],
    }

    # Try to get more details
    try:
        asset_detail = repo.get_asset(asset["id"])
        if hasattr(asset_detail, "asset_type"):
            result["type"] = asset_detail.asset_type
        if hasattr(asset_detail, "currency"):
            result["currency"] = asset_detail.currency
        if hasattr(asset_detail, "market_price"):
            result["last_price"] = asset_detail.market_price
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_TOOL_HANDLERS = {
    "get_portfolio_summary": _get_portfolio_summary,
    "get_positions": _get_positions,
    "get_target_drift": _get_target_drift,
    "get_performance": _get_performance,
    "get_cash_balance": _get_cash_balance,
    "get_recent_transactions": _get_recent_transactions,
    "get_portfolio_health": _get_portfolio_health,
    "get_day_movers": _get_day_movers,
    "get_monte_carlo": _get_monte_carlo,
    "calculate_rebalance_orders": _calculate_rebalance_orders,
    "calculate_what_if": _calculate_what_if,
    "calculate_pac_contribution": _calculate_pac_contribution,
    "search_asset_info": _search_asset_info,
}
