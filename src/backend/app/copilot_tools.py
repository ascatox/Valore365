"""Copilot Fase 2 — Tool definitions, executor, and computation logic.

Read-only tools that let the LLM agent fetch portfolio data on demand
and run server-side calculations (rebalance, what-if, PAC).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .services.performance_service import PerformanceService
from .repository import PortfolioRepository
from .services.portfolio_doctor import (
    analyze_portfolio_health,
    compute_weighted_ter,
    run_monte_carlo_projection,
    run_stress_test,
)
from .services.portfolio_doctor._holdings import _load_holdings

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
            "Cerca informazioni dettagliate su un asset per simbolo. "
            "Restituisce: nome, tipo, valuta, ISIN, TER (expense_ratio), settore, "
            "industria, paese, market cap, P/E, dividend yield, beta, 52w high/low, "
            "volumi, margini, fund family, categoria e descrizione."
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
    # --- T14: Dividend summary ---
    {
        "name": "get_dividend_summary",
        "description": (
            "Ottieni un riepilogo dei dividendi del portafoglio: dividendi ricevuti "
            "(totale storico e ultimi 12 mesi), dividend yield atteso del portafoglio, "
            "e proiezione del reddito annuo da dividendi."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T15: Cost breakdown ---
    {
        "name": "get_cost_breakdown",
        "description": (
            "Ottieni l'analisi dettagliata dei costi del portafoglio: TER per ogni "
            "posizione, TER ponderato totale, costo annuo stimato in EUR e fee drag "
            "proiettato a 10 anni. Utile per capire quanto costano gli ETF/fondi."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T16: X-Ray summary ---
    {
        "name": "get_xray_summary",
        "description": (
            "Ottieni l'X-Ray del portafoglio: titoli sottostanti aggregati degli ETF, "
            "esposizione geografica e settoriale, concentrazione su singoli titoli. "
            "Utile per capire cosa si possiede realmente attraverso gli ETF."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T17: Stress test ---
    {
        "name": "get_stress_test",
        "description": (
            "Ottieni lo stress test del portafoglio: impatto stimato di scenari storici "
            "(crisi 2008, COVID, dot-com, ecc.) e shock di mercato. Mostra il drawdown "
            "stimato per ogni scenario e il livello di rischio."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- T18: Income projection ---
    {
        "name": "get_income_projection",
        "description": (
            "Ottieni la proiezione del reddito da investimenti a 1, 3 e 5 anni. "
            "Considera dividendi attesi, crescita stimata e tassazione (capital gains tax). "
            "Utile per pianificazione FIRE e reddito passivo."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
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
    *,
    finance_client: object | None = None,
    justetf_client: object | None = None,
) -> dict:
    """Execute a tool by name and return a JSON-serializable dict."""
    try:
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {"error": f"Tool sconosciuto: {tool_name}"}
        return handler(
            tool_args, repo, perf_service, portfolio_id, user_id,
            finance_client=finance_client, justetf_client=justetf_client,
        )
    except Exception as exc:
        logger.exception("Tool execution error: %s", tool_name)
        return {"error": f"Errore nell'esecuzione del tool {tool_name}: {str(exc)}"}


# ---------------------------------------------------------------------------
# T1-T9: Informational tool handlers
# ---------------------------------------------------------------------------

def _get_portfolio_summary(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    summary = repo.get_summary(portfolio_id, user_id)
    return {
        "total_cash": round(summary.cash_balance, 2),
        "base_currency": summary.base_currency,
    }


def _get_recent_transactions(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    portfolio_id: int, user_id: str, **_kw: Any,
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
    _portfolio_id: int, _user_id: str, **_kw: Any,
) -> dict:
    """T13: Search asset info by symbol — returns rich metadata from DB."""
    symbol = args.get("symbol", "")
    if not symbol:
        return {"error": "Simbolo mancante"}

    asset = repo.get_asset_by_symbol(symbol)
    if not asset:
        return {"error": f"Asset non trovato per il simbolo: {symbol}"}

    result: dict = {
        "symbol": asset["symbol"],
        "name": asset["name"],
    }

    try:
        asset_detail = repo.get_asset(asset["id"])
        result["type"] = asset_detail.asset_type
        result["currency"] = asset_detail.quote_currency
        result["isin"] = asset_detail.isin
    except Exception:
        pass

    # Fetch stored metadata (TER, sector, etc.)
    try:
        meta = repo.get_asset_metadata(asset["id"])
        if meta:
            for field in [
                "expense_ratio", "fund_family", "total_assets", "category",
                "sector", "industry", "country", "market_cap",
                "trailing_pe", "forward_pe", "dividend_yield", "dividend_rate",
                "beta", "fifty_two_week_high", "fifty_two_week_low", "avg_volume",
                "profit_margins", "return_on_equity", "revenue_growth", "earnings_growth",
                "website",
            ]:
                val = getattr(meta, field, None)
                if val is not None:
                    result[field] = val
            if meta.description:
                # Truncate description to save tokens
                result["description"] = meta.description[:300]
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# T14-T18: Advanced analytical tool handlers
# ---------------------------------------------------------------------------

def _get_dividend_summary(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T14: Dividend analysis — received dividends, yield, income projection."""
    from datetime import date, timedelta

    # 1. Aggregate received dividends from transactions
    txns = repo.list_transactions(portfolio_id, user_id)
    dividend_txns = [t for t in txns if t.side == "dividend"]

    total_dividends = sum(float(t.quantity) * float(t.price) for t in dividend_txns)

    # Last 12 months
    one_year_ago = date.today() - timedelta(days=365)
    recent_divs = [
        t for t in dividend_txns
        if t.trade_at and t.trade_at.date() >= one_year_ago
    ]
    dividends_last_12m = sum(float(t.quantity) * float(t.price) for t in recent_divs)

    # 2. Expected yield from metadata
    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    total_mv = summary.market_value

    weighted_yield = 0.0
    position_yields: list[dict] = []
    for p in positions:
        try:
            asset = repo.get_asset_by_symbol(p.symbol)
            if not asset:
                continue
            meta = repo.get_asset_metadata(asset["id"])
            if meta and meta.dividend_yield:
                dy = float(meta.dividend_yield)
                weighted_yield += dy * (p.weight / 100.0)
                annual_income = p.market_value * dy / 100.0
                position_yields.append({
                    "symbol": p.symbol,
                    "dividend_yield_pct": round(dy, 2),
                    "annual_income_eur": round(annual_income, 2),
                })
        except Exception:
            continue

    # Sort by income descending, top 10
    position_yields.sort(key=lambda x: x["annual_income_eur"], reverse=True)

    projected_annual_income = total_mv * weighted_yield / 100.0

    return {
        "total_dividends_received": round(total_dividends, 2),
        "dividends_last_12m": round(dividends_last_12m, 2),
        "dividend_transactions_count": len(dividend_txns),
        "portfolio_weighted_yield_pct": round(weighted_yield, 2),
        "projected_annual_income_eur": round(projected_annual_income, 2),
        "projected_monthly_income_eur": round(projected_annual_income / 12, 2),
        "top_yielding_positions": position_yields[:10],
    }


def _get_cost_breakdown(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T15: Detailed cost/TER analysis."""
    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    total_mv = summary.market_value

    holdings = _load_holdings(repo, portfolio_id, user_id)
    weighted_ter = compute_weighted_ter(holdings, repo)

    # Per-position TER
    position_costs: list[dict] = []
    for p in positions:
        ter = None
        try:
            asset = repo.get_asset_by_symbol(p.symbol)
            if asset:
                # Try etf_enrichment first
                try:
                    enrichment = repo.get_etf_enrichment(asset["id"])
                    if enrichment and enrichment.get("ter") is not None:
                        ter = float(enrichment["ter"])
                except Exception:
                    pass
                # Fallback to asset_metadata
                if ter is None:
                    meta = repo.get_asset_metadata(asset["id"])
                    if meta and meta.expense_ratio is not None:
                        ter = float(meta.expense_ratio)
        except Exception:
            pass

        annual_cost = p.market_value * (ter / 100.0) if ter is not None else None
        position_costs.append({
            "symbol": p.symbol,
            "name": p.name,
            "weight_pct": round(p.weight, 2),
            "market_value": round(p.market_value, 2),
            "ter_pct": round(ter, 3) if ter is not None else None,
            "annual_cost_eur": round(annual_cost, 2) if annual_cost is not None else None,
        })

    # Sort by annual cost descending
    position_costs.sort(
        key=lambda x: x["annual_cost_eur"] if x["annual_cost_eur"] is not None else 0,
        reverse=True,
    )

    total_annual_cost = sum(
        c["annual_cost_eur"] for c in position_costs if c["annual_cost_eur"] is not None
    )

    # Fee drag projection: compound effect over 10 years
    # Simplified: cumulative cost assuming constant portfolio value
    fee_drag_10y = total_annual_cost * 10 if total_annual_cost else None
    # More accurate compound drag: value lost vs no-fee scenario
    if weighted_ter is not None and total_mv > 0:
        ter_decimal = weighted_ter / 100.0
        fee_drag_10y_compound = total_mv * (1 - (1 - ter_decimal) ** 10)
    else:
        fee_drag_10y_compound = None

    return {
        "weighted_ter_pct": round(weighted_ter, 3) if weighted_ter is not None else None,
        "total_annual_cost_eur": round(total_annual_cost, 2),
        "fee_drag_10y_eur": round(fee_drag_10y_compound, 2) if fee_drag_10y_compound is not None else None,
        "portfolio_market_value": round(total_mv, 2),
        "position_costs": position_costs[:20],
    }


def _get_xray_summary(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **kw: Any,
) -> dict:
    """T16: Portfolio X-Ray — underlying holdings, geographic/sector exposure."""
    from .services.portfolio_doctor import compute_portfolio_xray

    finance_client = kw.get("finance_client")
    justetf_client = kw.get("justetf_client")

    if not finance_client:
        return {"error": "X-Ray non disponibile: finance client non configurato."}

    xray = compute_portfolio_xray(
        repo, portfolio_id, user_id, finance_client, justetf_client,
    )

    # Top aggregated holdings (underlying stocks across ETFs)
    top_holdings = [
        {
            "symbol": h.symbol,
            "name": h.name,
            "aggregated_weight_pct": round(h.aggregated_weight_pct, 2),
        }
        for h in xray.aggregated_holdings[:15]
    ]

    # Geographic exposure
    geo = {k: round(v, 2) for k, v in xray.aggregated_country_exposure.items()}
    # Sort by weight descending, top 10
    geo_sorted = dict(sorted(geo.items(), key=lambda x: x[1], reverse=True)[:10])

    # Sector exposure
    sectors = {k: round(v, 2) for k, v in xray.aggregated_sector_exposure.items()}
    sectors_sorted = dict(sorted(sectors.items(), key=lambda x: x[1], reverse=True)[:10])

    return {
        "etf_count": xray.etf_count,
        "coverage_pct": round(xray.coverage_pct, 1),
        "top_underlying_holdings": top_holdings,
        "geographic_exposure": geo_sorted,
        "sector_exposure": sectors_sorted,
        "coverage_issues": [
            {"symbol": ci.symbol, "reason": ci.reason}
            for ci in xray.coverage_issues[:5]
        ],
    }


def _get_stress_test(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T17: Stress test — historical and shock scenarios."""
    result = run_stress_test(repo, portfolio_id, user_id)

    scenarios = []
    for s in result.scenarios:
        scenario_data: dict = {
            "scenario_name": s.scenario_name,
            "scenario_type": s.scenario_type,
            "period": s.period,
            "estimated_portfolio_impact_pct": round(s.estimated_portfolio_impact_pct, 2),
            "risk_level": s.risk_level,
        }
        if s.max_drawdown_pct is not None:
            scenario_data["max_drawdown_pct"] = round(s.max_drawdown_pct, 2)
        if s.recovery_months is not None:
            scenario_data["recovery_months"] = s.recovery_months
        if s.most_impacted_assets:
            scenario_data["most_impacted"] = [
                {"symbol": a.symbol, "loss_pct": round(a.estimated_loss_pct, 2)}
                for a in s.most_impacted_assets[:3]
            ]
        scenarios.append(scenario_data)

    # Sort by impact (most negative first)
    scenarios.sort(key=lambda s: s["estimated_portfolio_impact_pct"])

    return {
        "analysis_date": result.analysis_date,
        "portfolio_volatility_pct": (
            round(result.portfolio_volatility_pct, 2)
            if result.portfolio_volatility_pct is not None else None
        ),
        "scenarios": scenarios[:10],
    }


def _get_income_projection(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T18: Income projection — dividends at 1, 3, 5 years with growth and tax."""
    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    total_mv = summary.market_value

    # Get tax rate from user settings
    tax_rate = 26.0  # Default Italian capital gains tax
    try:
        user_settings = repo.get_user_settings(user_id)
        if user_settings.fire_capital_gains_tax_rate:
            tax_rate = float(user_settings.fire_capital_gains_tax_rate)
    except Exception:
        pass

    # Gather dividend yields
    total_annual_dividends = 0.0
    for p in positions:
        try:
            asset = repo.get_asset_by_symbol(p.symbol)
            if not asset:
                continue
            meta = repo.get_asset_metadata(asset["id"])
            if meta and meta.dividend_yield:
                dy = float(meta.dividend_yield) / 100.0
                total_annual_dividends += p.market_value * dy
        except Exception:
            continue

    # Assumed dividend growth rate (conservative estimate)
    dividend_growth_rate = 0.03  # 3% annual dividend growth

    projections = []
    for years in (1, 3, 5):
        # Project dividends with growth
        gross_income = 0.0
        for y in range(1, years + 1):
            gross_income += total_annual_dividends * (1 + dividend_growth_rate) ** y

        net_income = gross_income * (1 - tax_rate / 100.0)
        avg_annual_gross = gross_income / years
        avg_annual_net = net_income / years

        projections.append({
            "years": years,
            "cumulative_gross_eur": round(gross_income, 2),
            "cumulative_net_eur": round(net_income, 2),
            "avg_annual_gross_eur": round(avg_annual_gross, 2),
            "avg_annual_net_eur": round(avg_annual_net, 2),
        })

    yield_on_cost = 0.0
    if summary.cost_basis > 0:
        yield_on_cost = total_annual_dividends / summary.cost_basis * 100

    return {
        "current_annual_dividends_gross_eur": round(total_annual_dividends, 2),
        "current_annual_dividends_net_eur": round(
            total_annual_dividends * (1 - tax_rate / 100.0), 2,
        ),
        "current_monthly_net_eur": round(
            total_annual_dividends * (1 - tax_rate / 100.0) / 12, 2,
        ),
        "tax_rate_pct": tax_rate,
        "dividend_growth_assumption_pct": round(dividend_growth_rate * 100, 1),
        "yield_on_cost_pct": round(yield_on_cost, 2),
        "projections": projections,
    }


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
    "get_dividend_summary": _get_dividend_summary,
    "get_cost_breakdown": _get_cost_breakdown,
    "get_xray_summary": _get_xray_summary,
    "get_stress_test": _get_stress_test,
    "get_income_projection": _get_income_projection,
}
