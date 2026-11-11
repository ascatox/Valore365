"""Copilot Fase 2 — Tool definitions, executor, and computation logic.

Read-only tools that let the LLM agent fetch portfolio data on demand
and run server-side calculations (rebalance, what-if, PAC).
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from .services.performance_service import PerformanceService
from .repository import PortfolioRepository
from .repository._utilities import CASH_MODEL_NOTE
from .services.portfolio_doctor import (
    analyze_portfolio_health,
    run_monte_carlo_projection,
    run_stress_test,
)
from .services.portfolio_doctor._health import (
    CATEGORY_MAX_SCORES,
    health_volatility_info,
    resolve_holding_ters,
)
from .services.asset_classification import classify_asset, classify_asset_class
from .services.portfolio_doctor._holdings import load_classification_inputs
from .services.rebalance import (
    DEFAULT_TOLERANCE_PP,
    REBALANCE_MODES,
    RebalanceHolding,
    compute_rebalance_plan,
)
from .services.portfolio_doctor._holdings import _load_holdings
from .copilot_doctor_tools import DOCTOR_TOOL_DEFINITIONS, DOCTOR_TOOL_HANDLERS

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
            "P&L, variazione giornaliera, cash disponibile (modello di liquidita' della "
            "performance: acquisti scalati, vendite accreditate, mai negativa) e valuta base."
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
            "Ottieni la performance del portafoglio, TWR (time-weighted) e MWR (money-weighted, "
            "XIRR ACT/365), per 1 mese, 3 mesi, da inizio anno (YTD) e 1 anno. twr_<periodo> e "
            "mwr_<periodo> sono rendimenti di periodo in % (non annualizzati); include anche "
            "twr_annualized_pct, mwr_annualized_pct (solo finestre >= 365 giorni), mwr_converged, "
            "mwr_null_reason, mwr_multiple_roots, calculation_windows, implicit_contributions_eur "
            "e performance_note."
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
            "Ottieni il saldo cash disponibile nel portafoglio, con la valuta base, "
            "gli apporti impliciti cumulati e la scomposizione (depositi, acquisti, vendite...)."
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
            "Mostra id della transazione, data, tipo (buy/sell/deposit/withdrawal), simbolo, "
            "quantita', prezzo e importo totale. Righe identiche con id diversi "
            "sono transazioni distinte (es. possibili duplicati da import)."
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
            "nel portafoglio, con la variazione percentuale rispetto alla "
            "chiusura precedente. Esclude le posizioni con prezzo non aggiornato."
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
            "Ottieni le proiezioni Monte Carlo del portafoglio per gli anni 1-10. "
            "Include rendimento medio annualizzato, volatilita' e "
            "percentili (P25, P50, P75) per ogni anno, espressi come indice "
            "base 100 (valore iniziale = 100), non in euro."
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
            "il portafoglio al target (le vendite finanziano gli acquisti). Usa "
            "questo tool quando l'utente chiede come ribilanciare o tornare in target."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "available_cash": {
                    "type": "number",
                    "description": (
                        "Liquidita' AGGIUNTIVA in EUR (opzionale, default 0), sommata "
                        "alla liquidita' gia' presente nel portafoglio."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["rebalance", "buy_only", "sell_only"],
                    "default": "rebalance",
                    "description": (
                        "rebalance (default): vendite + acquisti autofinanziati; "
                        "buy_only: solo acquisti con la liquidita'; sell_only: solo vendite."
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
            "Versa solo sulle posizioni sotto-pesate, in proporzione allo scostamento "
            "dal target. Se nessuna posizione e' sotto il target restituisce "
            "distribuzione vuota, total_allocated 0, unallocated_amount e una nota."
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
            "volumi, margini, fund family, categoria e descrizione. "
            "Classificazione: asset_class (equity/bond/gold/commodity/cash/crypto/unknown, "
            "dal classificatore usato da stress test, salute, X-Ray e reddito) è il campo da usare "
            "per allocazione e rischio; instrument_type indica il veicolo (etc/etn/etf/fund/stock/"
            "bond/crypto/cash, null se non determinabile); classification_source la fonte della "
            "classe; type è il tipo tecnico salvato in anagrafica (es. un ETC sull'oro può avere "
            "type=stock)."
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
            "Utile per capire cosa si possiede realmente attraverso gli ETF. "
            "lookthrough_coverage_pct è la quota del portafoglio (liquidità esclusa) davvero scomposta; "
            "le esposizioni sommano a 100 con la quota 'Non classificato'; data_as_of è la data dei dati. "
            "applicable_lookthrough_coverage_pct è la quota scomposta della sola parte azionaria "
            "(applicable_denominator); not_applicable_pct (oro, materie prime, obbligazioni, monetario, cripto) "
            "e missing_pct (fondi azionari senza dati) distinguono 'non applicabile' da 'dati mancanti'; "
            "ogni fondo ha lookthrough_status (available/not_applicable/missing) e lookthrough_reason."
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
    # --- T19-T25: Portfolio Doctor 2.0 (policy, metrics, Scenario Lab) ---
    # Read-only / pure: no tool saves or restores a policy (contract §7).
    *DOCTOR_TOOL_DEFINITIONS,
]

_PAGE_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "dashboard": {
        "get_day_movers",
        "get_portfolio_health",
        "calculate_rebalance_orders",
        "calculate_what_if",
        "search_asset_info",
    },
    "portfolio": {
        "get_portfolio_health",
        "calculate_rebalance_orders",
        "calculate_what_if",
        "calculate_pac_contribution",
        "search_asset_info",
    },
    "doctor": {
        "get_portfolio_health",
        "get_cost_breakdown",
        "get_stress_test",
        "get_xray_summary",
        "search_asset_info",
        "read_doctor_policy",
        "read_doctor_metrics",
        "read_doctor_violations",
        "validate_policy_draft",
        "preview_policy",
        "build_doctor_scenario",
        "compare_doctor_scenarios",
    },
    "fire": {
        "get_portfolio_health",
        "get_dividend_summary",
        "get_income_projection",
        "get_monte_carlo",
        "search_asset_info",
    },
    "xray": {
        "get_xray_summary",
        "get_portfolio_health",
        "search_asset_info",
    },
    "transactions": {
        "get_recent_transactions",
        "get_dividend_summary",
        "search_asset_info",
    },
}


# ---------------------------------------------------------------------------
# Provider format conversion
# ---------------------------------------------------------------------------

# Without a (known) page_context every tool is offered except the Doctor
# tools: preview_policy emits a confirmation token and the Doctor tools are
# only meaningful (and only allowed) on the Doctor page.
_DOCTOR_TOOL_NAMES: frozenset[str] = frozenset(tool["name"] for tool in DOCTOR_TOOL_DEFINITIONS)
_DEFAULT_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    tool["name"] for tool in TOOL_DEFINITIONS if tool["name"] not in _DOCTOR_TOOL_NAMES
)


def get_allowed_tool_names_for_page_context(page_context: str | None) -> set[str]:
    """Tools offered on a page; missing/unknown page -> every non-Doctor tool."""
    allowed = _PAGE_TOOL_ALLOWLIST.get(page_context) if page_context else None
    return set(allowed) if allowed else set(_DEFAULT_TOOL_ALLOWLIST)


def build_tool_availability_block(page_context: str | None) -> str:
    # No block for a missing/unknown page (default allowlist), as before.
    allowed = _PAGE_TOOL_ALLOWLIST.get(page_context) if page_context else None
    if not allowed:
        return ""
    ordered_names = [tool["name"] for tool in TOOL_DEFINITIONS if tool["name"] in allowed]
    lines = [
        "--- TOOL DISPONIBILI IN QUESTA PAGINA ---",
        *(f"- {name}" for name in ordered_names),
        "Se una richiesta richiede analisi fuori da questa pagina, spiega che servono dati di un'altra sezione.",
        "--- FINE TOOL DISPONIBILI ---",
    ]
    return "\n".join(lines)


def format_tools_for_provider(provider: str, allowed_tool_names: set[str] | None = None) -> list[dict]:
    """Convert TOOL_DEFINITIONS to provider-specific format."""
    filtered_tools = [
        tool for tool in TOOL_DEFINITIONS
        if allowed_tool_names is None or tool["name"] in allowed_tool_names
    ]
    if provider == "anthropic":
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in filtered_tools
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
        for t in filtered_tools
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
    scope_portfolio_ids: list[int] | None = None,
    ui_events: list[dict] | None = None,
) -> dict:
    """Execute a tool by name and return a JSON-serializable dict.

    ``scope_portfolio_ids`` is the chat scope (aggregate view) used by the
    Doctor tools; ``ui_events`` collects events meant for the UI only (e.g.
    the ``policy_draft`` card carrying the confirmation token), which the
    caller emits on its own channel and never feeds back to the LLM.
    """
    try:
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {"error": f"Tool sconosciuto: {str(tool_name)[:100]}"}
        if not isinstance(tool_args, dict):
            tool_args = {}
        return handler(
            tool_args, repo, perf_service, portfolio_id, user_id,
            finance_client=finance_client, justetf_client=justetf_client,
            scope_portfolio_ids=scope_portfolio_ids, ui_events=ui_events,
        )
    except Exception as exc:
        logger.exception("Tool execution error: %s", tool_name)
        return {"error": f"Errore nell'esecuzione del tool {tool_name}: {str(exc)}"}


# ---------------------------------------------------------------------------
# T1-T9: Informational tool handlers
# ---------------------------------------------------------------------------

# TASK-47: data gaps are reported in the tool output, never hidden.
FX_MISSING_NOTE = (
    "Cambio mancante per {ccys}: gli importi in queste valute sono convertiti a 1,0 "
    "(liquidita'/costo) o le posizioni valutate al costo medio; i totali sono approssimati."
)
CASH_FX_MISSING_NOTE = (
    "Liquidita' approssimata: manca il cambio per {ccys} alla data dei movimenti, "
    "convertiti a 1,0."
)
STALE_PRICE_NOTE = (
    "Quotazione ferma per {symbols}: il prezzo non si aggiorna da almeno {sessions} sedute "
    "della borsa dell'asset (vedi stale_reason nelle posizioni); valore e variazione "
    "giornaliera di queste posizioni non sono aggiornati."
)
PRICE_FALLBACK_NOTE = (
    "Prezzo non disponibile (o senza cambio) per {symbols}: valore di mercato pari al "
    "costo medio, P/L non significativo."
)


def summary_data_flags(summary: Any) -> dict:
    """fx_missing_currencies / price_fallback_symbols of a summary, with an Italian note when non-empty."""
    fx_missing = list(getattr(summary, "fx_missing_currencies", None) or [])
    fallback = list(getattr(summary, "price_fallback_symbols", None) or [])
    stale = list(getattr(summary, "stale_price_symbols", None) or [])
    out: dict[str, Any] = {
        "fx_missing_currencies": fx_missing,
        "price_fallback_symbols": fallback,
        "stale_price_symbols": stale,
    }
    notes = []
    if fx_missing:
        notes.append(FX_MISSING_NOTE.format(ccys=", ".join(fx_missing)))
    if fallback:
        notes.append(PRICE_FALLBACK_NOTE.format(symbols=", ".join(fallback)))
    if stale:
        notes.append(STALE_PRICE_NOTE.format(symbols=", ".join(stale), sessions=_stale_max_sessions()))
    if notes:
        out["data_quality_note"] = " ".join(notes)
    return out


def position_row(p: Any) -> dict:
    """One position as the get_positions tools return it (shared with the aggregate MCP tool)."""
    return {
        "symbol": p.symbol,
        "name": p.name,
        "weight": round(p.weight, 2),
        "market_value": round(p.market_value, 2),
        "cost_basis": round(p.avg_cost * p.quantity, 2) if p.avg_cost else 0,
        "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
        "day_change_pct": round(p.day_change_pct, 2) if p.day_change_pct else 0,
        "quantity": float(p.quantity),
        "market_price": round(p.market_price, 4) if p.market_price else 0,
        "price_fallback": getattr(p, "price_fallback", None),
        "fx_missing": bool(getattr(p, "fx_missing", False)),
        # TASK-53: date of the daily close used as market_price, whether it is
        # stale (sessions of the asset's market) and why, latest provider tick.
        "price_date": _iso(getattr(p, "price_date", None)),
        "price_stale": bool(getattr(p, "price_stale", False)),
        "stale_reason": getattr(p, "stale_reason", None),
        "last_price_at": _iso(getattr(p, "last_price_at", None)),
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _stale_max_sessions() -> int:
    try:
        from .config import get_settings

        return int(get_settings().price_stale_max_sessions)
    except Exception:
        return 2


def positions_data_note(rows: list[dict]) -> dict:
    """Italian note for the positions whose price fell back to the average cost or is stale."""
    fallback = [r["symbol"] for r in rows if r.get("price_fallback")]
    stale = [r["symbol"] for r in rows if r.get("price_stale")]
    notes = []
    if fallback:
        notes.append(
            PRICE_FALLBACK_NOTE.format(symbols=", ".join(fallback))
            + " Per le posizioni con fx_missing manca il cambio della valuta di quotazione o di acquisto."
        )
    if stale:
        notes.append(STALE_PRICE_NOTE.format(symbols=", ".join(stale), sessions=_stale_max_sessions()))
    if not notes:
        return {}
    return {"data_quality_note": " ".join(notes)}


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
        "implicit_contributions_total": round(float(getattr(summary, "implicit_contributions_total", 0.0) or 0.0), 2),
        "cash_model_note": CASH_MODEL_NOTE,
        "base_currency": summary.base_currency,
        **summary_data_flags(summary),
    }


def _get_positions(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    positions = repo.get_positions(portfolio_id, user_id)
    sorted_pos = sorted(positions, key=lambda p: p.weight, reverse=True)[:30]
    rows = [position_row(p) for p in sorted_pos]
    return {"positions": rows, **positions_data_note(rows)}


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


PERFORMANCE_PERIODS: tuple[str, ...] = ("1m", "3m", "ytd", "1y")

PERFORMANCE_NOTE = (
    "twr_* e mwr_* sono rendimenti di PERIODO in percentuale (non annualizzati). "
    "TWR = time-weighted (neutralizza i flussi); MWR = money-weighted (XIRR, convenzione ACT/365). "
    "Le versioni annualizzate (twr_annualized_pct, mwr_annualized_pct) sono valorizzate solo per "
    "finestre di almeno 365 giorni. I valori sono di fine giornata: i flussi del giorno di inizio "
    "sono inclusi nel valore iniziale. Gli apporti impliciti sono trattati come versamenti esterni. "
    "Per piu' portafogli il calcolo avviene sui valori e flussi combinati, non come media dei singoli. "
    "mwr_null_reason spiega un MWR nullo ('non_convergente', 'non_calcolabile', 'errore_calcolo'); "
    "calculation_windows riporta le finestre effettive di TWR e MWR."
)


def _round2(value: Any) -> float | None:
    return round(float(value), 2) if value is not None else None


def _get_performance(
    _args: dict, _repo: PortfolioRepository, perf_service: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    result: dict = {}
    implicit: dict[str, float | None] = {}
    twr_annualized: dict[str, float | None] = {}
    mwr_annualized: dict[str, float | None] = {}
    mwr_converged: dict[str, bool | None] = {}
    mwr_null_reason: dict[str, str | None] = {}
    mwr_multiple_roots: dict[str, bool | None] = {}
    windows: dict[str, dict[str, Any] | None] = {}
    for period in PERFORMANCE_PERIODS:
        # One summary per period: TWR, MWR and windows all come from it.
        try:
            ps = perf_service.get_performance_summary(portfolio_id, user_id, period)
            result[f"twr_{period}"] = round(ps.twr.twr_pct, 2) if ps.twr.twr_pct is not None else None
            implicit[period] = round(float(getattr(ps, "implicit_contributions", 0.0) or 0.0), 2)
        except Exception:
            result[f"twr_{period}"] = None
            implicit[period] = None
            result[f"mwr_{period}"] = None
            twr_annualized[period] = None
            mwr_annualized[period] = None
            mwr_converged[period] = None
            mwr_null_reason[period] = "errore_calcolo"
            mwr_multiple_roots[period] = None
            windows[period] = None
            continue

        twr = getattr(ps, "twr", None)
        mwr = getattr(ps, "mwr", None)
        twr_annualized[period] = _round2(getattr(twr, "twr_annualized_pct", None))
        mwr_pct = getattr(mwr, "mwr_pct", None)
        converged = getattr(mwr, "converged", None)
        result[f"mwr_{period}"] = _round2(mwr_pct)
        mwr_annualized[period] = _round2(getattr(mwr, "mwr_annualized_pct", None))
        mwr_converged[period] = bool(converged) if converged is not None else None
        mwr_multiple_roots[period] = getattr(mwr, "multiple_roots", None)
        if mwr_pct is not None:
            mwr_null_reason[period] = None
        elif mwr is None:
            mwr_null_reason[period] = "errore_calcolo"
        elif converged is False:
            mwr_null_reason[period] = "non_convergente"
        else:
            mwr_null_reason[period] = "non_calcolabile"
        windows[period] = {
            "start_date": getattr(ps, "start_date", None),
            "end_date": getattr(ps, "end_date", None),
            "period_days": getattr(ps, "period_days", None),
            "twr_start_date": getattr(twr, "start_date", None),
            "twr_end_date": getattr(twr, "end_date", None),
            "mwr_start_date": getattr(mwr, "start_date", None),
            "mwr_end_date": getattr(mwr, "end_date", None),
        }
    result["implicit_contributions_eur"] = implicit
    result["implicit_contributions_note"] = (
        "Apporti impliciti per periodo (valuta base): acquisti o uscite oltre la liquidita' "
        "registrata, trattati come versamenti esterni nel TWR/MWR (non come rendimento)."
    )
    result["twr_annualized_pct"] = twr_annualized
    result["mwr_annualized_pct"] = mwr_annualized
    result["mwr_converged"] = mwr_converged
    result["mwr_null_reason"] = mwr_null_reason
    result["mwr_multiple_roots"] = mwr_multiple_roots
    result["calculation_windows"] = windows
    result["performance_note"] = PERFORMANCE_NOTE
    return result


def _get_cash_balance(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    # Same number and rule as summary.cash_balance, GET /cash-balance
    # total_cash and the performance (TASK-47, TASK-49): the cash model folded
    # over every transaction at the trade-date FX, never negative.
    cash = repo.get_current_cash_balance_detail(portfolio_id, user_id)
    out: dict[str, Any] = {
        "total_cash": round(cash.balance, 2),
        "base_currency": repo.get_portfolio_base_currency(portfolio_id, user_id),
        "implicit_contributions_total": round(float(getattr(cash, "implicit_contributions", 0.0) or 0.0), 2),
        "cash_breakdown": dict(getattr(cash, "components", None) or {}),
        "cash_model_note": CASH_MODEL_NOTE,
    }
    # Only the cash gaps here (the summary also lists the positions' ones).
    missing = list(cash.fx_missing_currencies)
    out["fx_missing_currencies"] = missing
    if missing:
        out["data_quality_note"] = CASH_FX_MISSING_NOTE.format(ccys=", ".join(missing))
    return out


def _get_recent_transactions(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    txns = repo.list_transactions(portfolio_id, user_id)[:20]
    return {
        "transactions": [
            {
                "id": t.id,
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
        # Methodology of portfolio_volatility (TASK-40): weighted average of
        # single-asset realized volatility, no correlations, never floored.
        "volatility": (
            doctor.volatility.model_dump()
            if doctor.volatility is not None
            else health_volatility_info(doctor.metrics.portfolio_volatility).model_dump()
        ),
        # Score = sum of category scores; each category starts at its max and
        # loses the points listed in score_deductions.
        "category_scores": doctor.category_scores.model_dump(),
        "category_max_scores": dict(CATEGORY_MAX_SCORES),
        "score_deductions": [d.model_dump() for d in doctor.score_deductions],
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
    """Best/worst daily change among the portfolio positions.

    Computed from repo.get_positions (day_change_pct = current price vs
    previous close, in quote currency). Positions with a stale price, no
    price at all or no previous close are excluded: their day_change_pct is
    the 0.0 default, not a real change. A 0.0 on a fresh price with a
    previous close is valid data (flat day).
    """
    positions = repo.get_positions(portfolio_id, user_id) or []
    valid = []
    excluded = 0
    excluded_no_prev = 0
    # TASK-53: which positions were left out for a stale price, and why.
    stale_positions: list[dict] = []
    for p in positions:
        change = p.day_change_pct
        if (
            p.price_stale
            or p.price_date is None
            or change is None
            or not math.isfinite(change)
        ):
            excluded += 1
            if p.price_stale or p.price_date is None:
                stale_positions.append({
                    "symbol": p.symbol,
                    "price_date": _iso(p.price_date),
                    "stale_reason": getattr(p, "stale_reason", None)
                    or ("nessuna quotazione giornaliera disponibile" if p.price_date is None else None),
                })
            continue
        if not getattr(p, "previous_close_available", False):
            excluded_no_prev += 1
            continue
        valid.append(p)

    if not valid:
        if not positions:
            reason = "Nessuna posizione nel portafoglio."
        elif excluded_no_prev:
            reason = (
                "Nessuna posizione con prezzo aggiornato e chiusura precedente: "
                "variazione giornaliera non disponibile."
            )
        else:
            reason = "Nessuna posizione con prezzo aggiornato: variazione giornaliera non disponibile."
        return {
            "best": None,
            "worst": None,
            "reason": reason,
            "valid_positions": 0,
            "excluded_stale": excluded,
            "excluded_no_previous_close": excluded_no_prev,
            "stale_positions": stale_positions,
        }

    def _mover(p: Any) -> dict:
        return {
            "symbol": p.symbol,
            "name": p.name,
            "day_change_pct": round(p.day_change_pct, 2),
            "price_date": p.price_date.isoformat() if p.price_date else None,
        }

    # Stable ordering: ties broken by symbol (alphabetical) for both ends.
    best = min(valid, key=lambda p: (-p.day_change_pct, p.symbol))
    worst = min(valid, key=lambda p: (p.day_change_pct, p.symbol))
    return {
        "best": _mover(best),
        "worst": _mover(worst),
        "valid_positions": len(valid),
        "excluded_stale": excluded,
        "excluded_no_previous_close": excluded_no_prev,
        "stale_positions": stale_positions,
    }


_MC_YEARS = range(1, 11)


def _get_monte_carlo(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    mc = run_monte_carlo_projection(repo, portfolio_id, user_id)
    projections = sorted(
        (p for p in mc.projections if p.year in _MC_YEARS),
        key=lambda p: p.year,
    )
    return {
        "annualized_mean_return_pct": round(mc.annualized_mean_return_pct, 2),
        "annualized_volatility_pct": round(mc.annualized_volatility_pct, 2),
        "return_assumption": "rendimento atteso di lungo periodo per classe di attivo (ipotesi prudenziale, non derivato dalla performance recente)",
        "unit": "indice_base_100",
        "initial_value": 100,
        "unit_note": (
            "I percentili sono un indice con valore iniziale 100 (anno 0), non importi in euro: "
            "ad esempio 120 significa +20% rispetto al valore attuale del portafoglio."
        ),
        "projections": [
            {"year": p.year, "p25": p.p25, "p50": p.p50, "p75": p.p75}
            for p in projections
        ],
    }


# ---------------------------------------------------------------------------
# T10-T12: Computation tool handlers
# ---------------------------------------------------------------------------

def _calculate_rebalance_orders(
    args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T10: buy/sell orders to realign the portfolio to target (TASK-39).

    Self-financing by default (mode ``rebalance``): sells first, proceeds fund
    the buys. Portfolio cash + ``available_cash`` (extra) are part of the total
    and of the weights. See app.services.rebalance for the algorithm.
    """
    mode = args.get("mode") or "rebalance"
    if mode not in REBALANCE_MODES:
        return {"error": f"mode non valida: {mode}. Valori ammessi: rebalance, buy_only, sell_only"}
    extra_cash = args.get("available_cash")
    if extra_cash is None:
        extra_cash = 0.0
    try:
        extra_cash = float(extra_cash)
    except (TypeError, ValueError):
        return {"error": "available_cash deve essere un numero >= 0"}
    if not math.isfinite(extra_cash) or extra_cash < 0:
        return {"error": "available_cash deve essere un numero >= 0"}

    summary = repo.get_summary(portfolio_id, user_id)
    positions = repo.get_positions(portfolio_id, user_id) or []
    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    except Exception:
        target_alloc = []
    if not target_alloc:
        return {"mode": mode, "orders": [], "note": "Nessun target configurato."}

    targets = {t.asset_id: t for t in target_alloc}
    pos_by_asset = {p.asset_id: p for p in positions}
    holdings = [
        RebalanceHolding(
            key=p.asset_id, symbol=p.symbol, current_value=float(p.market_value or 0.0),
            target_weight_pct=float(targets[p.asset_id].weight_pct) if p.asset_id in targets else None,
        )
        for p in positions
    ]
    holdings += [
        RebalanceHolding(key=t.asset_id, symbol=t.symbol, current_value=0.0, target_weight_pct=float(t.weight_pct))
        for t in target_alloc
        if t.asset_id not in pos_by_asset
    ]
    portfolio_cash = float(summary.cash_balance or 0.0)
    plan = compute_rebalance_plan(
        holdings,
        portfolio_cash=portfolio_cash,
        extra_cash=extra_cash,
        mode=mode,
        tolerance_pp=DEFAULT_TOLERANCE_PP,
    )

    orders = []
    for o in plan.orders:
        pos = pos_by_asset.get(o.key)
        price = pos.market_price if pos and pos.market_price else None
        amount = round(o.amount, 2)
        orders.append({
            "side": o.side,
            "symbol": o.symbol,
            "amount_eur": amount,
            "shares_approx": round(amount / price, 4) if price and price > 0 else None,
            "current_weight_pct": round(o.current_weight_pct, 2),
            "target_weight_pct": round(o.target_weight_pct, 2),
            "weight_after_pct": round(o.weight_after_pct, 2),
        })

    sells = round(sum(o["amount_eur"] for o in orders if o["side"] == "sell"), 2)
    buys = round(sum(o["amount_eur"] for o in orders if o["side"] == "buy"), 2)
    cash_before = round(plan.portfolio_cash, 2)
    extra = round(plan.extra_cash, 2)
    cash_after = round(cash_before + extra + sells - buys, 2)
    invariant_ok = cash_after >= 0 and abs(cash_after - plan.cash_after) <= 0.01 * (len(orders) + 1)

    notes = [
        "Le commissioni e le imposte non sono modellate: importi lordi.",
        f"Banda di tolleranza {DEFAULT_TOLERANCE_PP} pp sul peso: se nessuno strumento la supera "
        "non ci sono ordini; altrimenti tutti gli strumenti tornano al target.",
        "La liquidita' del portafoglio (stesso modello della performance: acquisti scalati, vendite "
        "accreditate) e available_cash (liquidita' aggiuntiva) entrano nel totale e nei pesi.",
    ]
    if portfolio_cash < 0:
        notes.append("Saldo di liquidita' negativo considerato pari a 0.")
    if plan.untargeted_symbols:
        notes.append(
            "Posizioni senza target lasciate invariate ed escluse dal totale: "
            "i pesi target si applicano al valore restante."
        )
    if plan.unallocated_target_pct > 0.005:
        notes.append(
            f"I target sommano a {plan.target_sum_pct:.2f}%: il restante "
            f"{plan.unallocated_target_pct:.2f}% resta in liquidita'."
        )
    if plan.buys_scaled:
        notes.append("Liquidita' insufficiente: acquisti ridotti in proporzione al fabbisogno.")
    if not orders:
        notes.append("Nessun ordine necessario: portafoglio entro la banda di tolleranza.")

    return {
        "mode": mode,
        "orders": orders,
        "totals": {
            "sells_eur": sells,
            "buys_eur": buys,
            "cash_before": cash_before,
            "extra_cash": extra,
            "cash_after": cash_after,
            "invariant": "cash_after = cash_before + extra_cash + sells_eur - buys_eur",
            "invariant_ok": invariant_ok,
        },
        "total_value": round(plan.base_value, 2),
        "tolerance_pp": DEFAULT_TOLERANCE_PP,
        "untargeted_holdings": plan.untargeted_symbols,
        "untargeted_value": round(plan.untargeted_value, 2),
        "target_sum_pct": round(plan.target_sum_pct, 2),
        "unallocated_target_pct": round(plan.unallocated_target_pct, 2),
        "notes": notes,
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

    # TASK-83: the amount is split in whole cents, so the rows always add up
    # exactly to ``total_allocated`` and nothing is declared allocated without
    # a destination.
    total_cents = int(round(float(monthly_amount) * 100))
    if total_cents <= 0:
        return {"error": "Importo mensile deve essere almeno 0,01 EUR"}
    underweight = [a for a in assets_with_drift if a["drift"] < 0]
    if not underweight:
        # No instrument is below its target (all at target or above, e.g. when
        # the targets add up to less than 100): there is no declared rule to
        # pick a destination, so nothing is allocated and the note says why.
        target_sum = sum(ta.weight_pct for ta in target_alloc)
        note = (
            "Nessuno strumento è sotto il proprio peso obiettivo: l'importo non è "
            "stato distribuito (totale allocato 0)."
        )
        if target_sum < 100 - 0.01:
            note += (
                f" I pesi obiettivo sommano a {round(target_sum, 2)}% invece di 100%: "
                "completa i target per ricevere una ripartizione del PAC."
            )
        else:
            note += (
                " Per mantenere il portafoglio sui target puoi ripartire il versamento "
                "in proporzione ai pesi obiettivo."
            )
        return {
            "monthly_amount": monthly_amount,
            "distribution": [],
            "total_allocated": 0.0,
            "unallocated_amount": round(total_cents / 100, 2),
            "note": note,
        }

    # Distribute proportionally to the negative drift (largest remainder on cents).
    total_negative_drift = sum(-a["drift"] for a in underweight)
    raw_cents = [(-a["drift"]) / total_negative_drift * total_cents for a in underweight]
    cents = [int(c) for c in raw_cents]
    leftover = total_cents - sum(cents)
    by_remainder = sorted(range(len(underweight)), key=lambda i: (cents[i] - raw_cents[i], i))
    for i in by_remainder[:leftover]:
        cents[i] += 1

    new_total = total_value + total_cents / 100
    distribution = []
    for asset, c in zip(underweight, cents):
        if c <= 0:
            continue
        amount = c / 100
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

    return {
        "monthly_amount": monthly_amount,
        "distribution": distribution,
        "total_allocated": round(sum(cents) / 100, 2),
        "unallocated_amount": 0.0,
    }


def _held_asset_id(repo: PortfolioRepository, portfolio_id: int, user_id: str, symbol: str) -> int | None:
    """asset_id of a symbol held or traded in the portfolio (exact, case-insensitive)."""
    wanted = symbol.strip().upper()
    try:
        for p in repo.get_positions(portfolio_id, user_id) or []:
            if str(p.symbol).upper() == wanted:
                return int(p.asset_id)
    except Exception:
        pass
    try:
        for t in repo.list_transactions(portfolio_id, user_id) or []:
            t_symbol = getattr(t, "symbol", None)
            t_asset = getattr(t, "asset_id", None)
            if t_symbol and t_asset and str(t_symbol).upper() == wanted:
                return int(t_asset)
    except Exception:
        pass
    return None


def _search_asset_info(
    args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T13: Search asset info by symbol — returns rich metadata from DB.

    A symbol held (or traded) in the portfolio is resolved by exact symbol
    to its asset_id. Only other symbols go through get_asset_by_symbol,
    whose base-ticker match can return another listing: that case is
    flagged (match=different_listing + warning), never silent (TASK-44).
    """
    symbol = str(args.get("symbol", "") or "").strip()
    if not symbol:
        return {"error": "Simbolo mancante"}

    asset_id = _held_asset_id(repo, portfolio_id, user_id, symbol)
    if asset_id is not None:
        asset = {"id": asset_id, "symbol": symbol.upper(), "name": ""}
        match = "portfolio"
    else:
        asset = repo.get_asset_by_symbol(symbol)
        if not asset:
            return {"error": f"Asset non trovato per il simbolo: {symbol}"}
        match = "exact" if str(asset["symbol"]).upper() == symbol.upper() else "different_listing"

    result: dict = {
        "symbol": asset["symbol"],
        "name": asset["name"],
        "match": match,
    }

    try:
        asset_detail = repo.get_asset(asset["id"])
        result["symbol"] = asset_detail.symbol or result["symbol"]
        if getattr(asset_detail, "name", None):
            result["name"] = asset_detail.name
        result["type"] = asset_detail.asset_type
        # Quote currency of the listing as stored for the asset (not the
        # currency of an amount: this tool returns no amounts).
        result["currency"] = asset_detail.quote_currency
        result["isin"] = asset_detail.isin
    except Exception:
        pass

    if match == "different_listing":
        result["requested_symbol"] = symbol
        result["warning"] = (
            f"Nessun asset con simbolo esatto {symbol}: i dati si riferiscono a "
            f"{result['symbol']}, un altro listing con lo stesso ticker base."
        )

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
        meta = None

    result.update(_asset_info_classification(repo, asset["id"], result, meta))
    return result


ASSET_CLASS_NOTE = (
    "Per allocazione e rischio usa asset_class (stessa classificazione di stress test, "
    "salute, X-Ray e reddito). type è il tipo tecnico salvato in anagrafica e può "
    "differire (es. un ETC sull'oro registrato come stock)."
)


def _asset_info_classification(repo: PortfolioRepository, asset_id: int, info: dict, meta: Any) -> dict:
    """asset_class / instrument_type / classification_source for
    search_asset_info (TASK-51), from the shared classifier and the stored
    justETF enrichment. Read-only: nothing is fetched from providers."""
    try:
        enrichment = repo.get_etf_enrichment(asset_id)
    except Exception:
        enrichment = None
    if not isinstance(enrichment, dict):
        enrichment = {}

    def _text(value: Any) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    classification = classify_asset(
        asset_type=_text(info.get("type")),
        name=_text(info.get("name")),
        symbol=_text(info.get("symbol")),
        isin=_text(info.get("isin")) or _text(enrichment.get("isin")),
        investment_focus=_text(enrichment.get("investment_focus")),
        index_tracked=_text(enrichment.get("index_tracked")),
        category=_text(getattr(meta, "category", None)),
        enrichment_name=_text(enrichment.get("name")),
    )
    return {
        "asset_class": classification.asset_class,
        "instrument_type": classification.instrument_type,
        "classification_source": classification.source,
        "classification_note": ASSET_CLASS_NOTE,
    }


# ---------------------------------------------------------------------------
# T14-T18: Advanced analytical tool handlers
# ---------------------------------------------------------------------------

def _get_dividend_summary(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T14: Dividend analysis — received dividends, yield, income projection."""
    from datetime import date, timedelta

    # 1. Aggregate received dividends from transactions, per currency: no FX
    # helper is available here, so amounts in different currencies are never
    # summed together (TASK-44).
    txns = repo.list_transactions(portfolio_id, user_id)
    dividend_txns = [t for t in txns if t.side == "dividend"]
    one_year_ago = date.today() - timedelta(days=365)

    by_currency: dict[str, dict] = {}
    for t in dividend_txns:
        ccy = str(getattr(t, "trade_currency", None) or "").upper() or "N/D"
        amount = float(t.quantity) * float(t.price)
        bucket = by_currency.setdefault(ccy, {"total": 0.0, "last_12m": 0.0, "count": 0})
        bucket["total"] += amount
        bucket["count"] += 1
        if t.trade_at and t.trade_at.date() >= one_year_ago:
            bucket["last_12m"] += amount
    dividends_by_currency = {
        ccy: {"total": round(v["total"], 2), "last_12m": round(v["last_12m"], 2), "count": v["count"]}
        for ccy, v in sorted(by_currency.items())
    }
    mixed_currencies = len(by_currency) > 1
    if mixed_currencies:
        total_dividends: float | None = None
        dividends_last_12m: float | None = None
    else:
        only = next(iter(by_currency.values()), {"total": 0.0, "last_12m": 0.0})
        total_dividends = only["total"]
        dividends_last_12m = only["last_12m"]

    # 2. Expected yield from metadata, matched by the position's asset_id
    # (not by the loose base-ticker symbol lookup).
    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    total_mv = summary.market_value

    weighted_yield = 0.0
    position_yields: list[dict] = []
    for p in positions:
        try:
            meta = repo.get_asset_metadata(p.asset_id)
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

    result = {
        "total_dividends_received": round(total_dividends, 2) if total_dividends is not None else None,
        "dividends_last_12m": round(dividends_last_12m, 2) if dividends_last_12m is not None else None,
        "dividends_currency": None if mixed_currencies else next(iter(by_currency), None),
        "dividends_by_currency": dividends_by_currency,
        "mixed_currencies": mixed_currencies,
        "dividend_transactions_count": len(dividend_txns),
        "portfolio_weighted_yield_pct": round(weighted_yield, 2),
        "projected_annual_income_eur": round(projected_annual_income, 2),
        "projected_monthly_income_eur": round(projected_annual_income / 12, 2),
        "top_yielding_positions": position_yields[:10],
    }
    if mixed_currencies:
        result["currency_note"] = (
            "Dividendi in più valute: i totali non sono sommati senza conversione FX; "
            "usa dividends_by_currency (importi nella valuta di ciascuna transazione)."
        )
    return result


def _get_cost_breakdown(
    _args: dict, repo: PortfolioRepository, _perf: PerformanceService,
    portfolio_id: int, user_id: str, **_kw: Any,
) -> dict:
    """T15: Detailed cost/TER analysis.

    TER per position comes from ``resolve_holding_ters`` (same source as
    ``compute_weighted_ter``): justETF → yFinance (normalized) → inferred.
    All cost figures share one declared perimeter: the *covered* positions
    (TER known or inferred). ``weighted_ter_pct`` is weighted on the covered
    weight, ``estimated_annual_cost_known_eur`` (alias of the legacy
    ``total_annual_cost_eur``) sums the covered positions only, and
    ``fee_drag_10y_eur`` is computed on ``covered_market_value_eur``.
    ``ter_coverage_pct`` is the covered share of the non-cash market value.
    """
    positions = repo.get_positions(portfolio_id, user_id)
    summary = repo.get_summary(portfolio_id, user_id)
    total_mv = summary.market_value

    holdings = _load_holdings(repo, portfolio_id, user_id)
    resolved = resolve_holding_ters(holdings, repo)
    asset_type_by_id = {h.asset_id: (h.asset_type or "").lower() for h in holdings}

    position_costs: list[dict] = []
    covered_mv = 0.0
    weighted_sum = 0.0
    known_cost = 0.0
    non_cash_mv = 0.0
    covered_non_cash_mv = 0.0
    missing: list[str] = []
    inferred: list[str] = []
    for p in positions:
        ter, source = resolved.get(p.asset_id, (None, "none"))
        asset_type = asset_type_by_id.get(p.asset_id) or (p.asset_type or "").lower()
        is_cash = asset_type == "cash"
        mv = float(p.market_value or 0.0)
        annual_cost = mv * (ter / 100.0) if ter is not None else None
        if ter is not None:
            covered_mv += mv
            weighted_sum += mv * ter
            known_cost += annual_cost
            if source == "inferred":
                inferred.append(p.symbol)
        if not is_cash:
            non_cash_mv += mv
            if ter is not None:
                covered_non_cash_mv += mv
            else:
                missing.append(p.symbol)
        position_costs.append({
            "symbol": p.symbol,
            "name": p.name,
            "weight_pct": round(p.weight, 2),
            "market_value": round(mv, 2),
            "ter_pct": round(ter, 3) if ter is not None else None,
            "ter_source": source,
            "annual_cost_eur": round(annual_cost, 2) if annual_cost is not None else None,
        })

    # Sort by annual cost descending
    position_costs.sort(
        key=lambda x: x["annual_cost_eur"] if x["annual_cost_eur"] is not None else 0,
        reverse=True,
    )

    has_coverage = covered_mv > 0
    weighted_ter = weighted_sum / covered_mv if has_coverage else None
    estimated_known = round(known_cost, 2) if has_coverage else None
    # Compound drag over 10 years on the same covered perimeter.
    fee_drag_10y = (
        covered_mv * (1 - (1 - weighted_ter / 100.0) ** 10) if weighted_ter is not None else None
    )
    ter_coverage_pct = (
        round(covered_non_cash_mv / non_cash_mv * 100.0, 1) if non_cash_mv > 0 else None
    )

    coverage_note = None
    if ter_coverage_pct is not None and ter_coverage_pct < 100.0:
        coverage_note = (
            f"TER disponibile per il {ter_coverage_pct:.1f}% del valore investito (liquidità esclusa). "
            f"TER ponderato, costo annuo e fee drag si riferiscono solo alle posizioni coperte"
            + (f"; mancano: {', '.join(missing)}." if missing else ".")
        )

    return {
        "weighted_ter_pct": round(weighted_ter, 3) if weighted_ter is not None else None,
        # Legacy key: same value as estimated_annual_cost_known_eur (covered positions only).
        "total_annual_cost_eur": estimated_known,
        "estimated_annual_cost_known_eur": estimated_known,
        "fee_drag_10y_eur": round(fee_drag_10y, 2) if fee_drag_10y is not None else None,
        "cost_perimeter": "covered_positions",
        "covered_market_value_eur": round(covered_mv, 2),
        "portfolio_market_value": round(total_mv, 2),
        "ter_coverage_pct": ter_coverage_pct,
        "missing_ter_symbols": missing,
        "inferred_ter_symbols": inferred,
        "coverage_note": coverage_note,
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

    from .services.portfolio_doctor._xray import UNCLASSIFIED_LABEL

    def _top_summing_to_100(dist: dict[str, float], limit: int = 10) -> dict[str, float]:
        """Top buckets, the rest grouped in "Altri", unclassified always explicit,
        so the truncated distribution still sums to 100 (TASK-48)."""
        named = sorted(
            ((k, v) for k, v in dist.items() if k != UNCLASSIFIED_LABEL),
            key=lambda x: x[1], reverse=True,
        )
        out = {k: round(v, 2) for k, v in named[:limit]}
        rest = sum(v for _, v in named[limit:])
        if rest > 0:
            out["Altri"] = round(out.get("Altri", 0.0) + rest, 2)
        if dist.get(UNCLASSIFIED_LABEL):
            out[UNCLASSIFIED_LABEL] = round(dist[UNCLASSIFIED_LABEL], 2)
        return out

    return {
        # TASK-87: no positions -> empty X-Ray declared here and in coverage_note, not an error.
        "is_empty": xray.is_empty,
        "etf_count": xray.etf_count,
        # Legacy: same as funds_with_holdings_pct (weight of funds with some top holdings).
        "coverage_pct": round(xray.coverage_pct, 1),
        "lookthrough_coverage_pct": xray.lookthrough_coverage_pct,
        # TASK-52: coverage of the applicable (equity) part and status shares.
        "applicable_lookthrough_coverage_pct": xray.applicable_lookthrough_coverage_pct,
        "applicable_denominator": xray.applicable_denominator,
        "available_pct": xray.available_pct,
        "not_applicable_pct": xray.not_applicable_pct,
        "missing_pct": xray.missing_pct,
        "funds_with_holdings_pct": xray.funds_with_holdings_pct,
        "classified_country_pct": xray.classified_country_pct,
        "classified_sector_pct": xray.classified_sector_pct,
        "coverage_denominator": xray.coverage_denominator,
        "coverage_note": xray.coverage_note,
        "data_as_of": xray.data_as_of,
        "top_underlying_holdings": top_holdings,
        # Geographic / sector exposure: sum to 100 over coverage_denominator.
        "geographic_exposure": _top_summing_to_100(xray.aggregated_country_exposure),
        "sector_exposure": _top_summing_to_100(xray.aggregated_sector_exposure),
        "funds": [
            {
                "symbol": d.symbol,
                "portfolio_weight_pct": d.portfolio_weight_pct,
                "lookthrough_kind": d.lookthrough_kind,
                "lookthrough_status": d.lookthrough_status,
                "lookthrough_reason": d.lookthrough_reason,
                "listed_holdings_pct": d.listed_holdings_pct,
                "source": d.data_source,
                "data_as_of": d.data_as_of,
            }
            for d in xray.etf_details[:20]
        ],
        "coverage_issues": [
            {
                "symbol": ci.symbol,
                "reason": ci.reason,
                "lookthrough_status": ci.lookthrough_status,
            }
            # Missing data first: not_applicable positions are not a data gap.
            for ci in sorted(xray.coverage_issues, key=lambda ci: ci.lookthrough_status != "missing")[:5]
        ],
        "coverage_issues_total": len(xray.coverage_issues),
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
                {
                    "symbol": a.symbol,
                    "loss_pct": round(a.estimated_loss_pct, 2),
                    **({"asset_class": a.asset_class} if a.asset_class else {}),
                }
                for a in s.most_impacted_assets[:3]
            ]
        if s.scenario_type == "shock":
            # Classes hit, shock per class and contribution (weight x shock).
            scenario_data["affected_classes"] = list(s.affected_classes)
            scenario_data["class_breakdown"] = [
                {
                    "asset_class": row.asset_class,
                    "weight_pct": row.weight_pct,
                    "shock_pct": row.shock_pct,
                    "contribution_pct": row.contribution_pct,
                }
                for row in s.class_breakdown
            ]
        else:
            # Historical: method (historical/proxy/not_available), weight
            # covered by real prices and per-class drawdown with its source.
            scenario_data["method"] = s.method
            scenario_data["coverage_pct"] = s.coverage_pct
            if s.methodology_note:
                scenario_data["methodology_note"] = s.methodology_note
            scenario_data["class_breakdown"] = [
                {
                    "asset_class": row.asset_class,
                    "weight_pct": row.weight_pct,
                    "drawdown_pct": row.drawdown_pct,
                    "contribution_pct": row.contribution_pct,
                    "source": row.source,
                }
                for row in s.class_breakdown
            ]
        if s.flags:
            scenario_data["flags"] = list(s.flags)
        scenarios.append(scenario_data)

    # Sort by impact (most negative first)
    scenarios.sort(key=lambda s: s["estimated_portfolio_impact_pct"])

    return {
        "analysis_date": result.analysis_date,
        "portfolio_volatility_pct": (
            round(result.portfolio_volatility_pct, 2)
            if result.portfolio_volatility_pct is not None else None
        ),
        # Methodology of portfolio_volatility_pct (TASK-40): realized 1y
        # portfolio volatility floored at the long-term class-mix volatility.
        "volatility": result.volatility.model_dump() if result.volatility is not None else None,
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

    # Gather dividend yields, split by asset class (shared classifier, TASK-36)
    # for differentiated growth. Classification uses the position's own
    # asset_type / investment_focus and the metadata category, matched by
    # asset_id: get_asset_by_symbol returns only id/symbol/name, so reading
    # asset_type from it put every instrument in equity (V365-004).
    EQUITY_GROWTH_RATE = 0.03   # 3% annual dividend growth for equity-like assets
    # Coupons don't grow. Inflation-linked bonds (e.g. FRC3-like) also get 0%:
    # their growth is an open decision (TASK-36), stated in the output.
    FIXED_INCOME_GROWTH_RATE = 0.0
    # Gold/commodity/cash/crypto/unknown: no growth assumed (prudential).
    OTHER_GROWTH_RATE = 0.0
    bucket_of_class = {"equity": "equity", "bond": "fixed_income"}

    try:
        metadata_by_asset = repo.get_asset_metadata_bulk([p.asset_id for p in positions])
    except Exception:
        metadata_by_asset = {}
    # Same stored inputs as the Doctor holdings (TASK-50): ISIN and justETF
    # enrichment (investment_focus, index_tracked, official name).
    try:
        inputs_by_asset = load_classification_inputs(repo, [p.asset_id for p in positions])
    except Exception:
        inputs_by_asset = {}

    bucket_dividends = {"equity": 0.0, "fixed_income": 0.0, "other_or_unknown": 0.0}
    unknown_symbols: list[str] = []
    missing_yield_symbols: list[str] = []
    for p in positions:
        meta = metadata_by_asset.get(p.asset_id)
        inputs = inputs_by_asset.get(p.asset_id, {})
        asset_class = classify_asset_class(
            asset_type=getattr(p, "asset_type", None),
            name=p.name,
            symbol=p.symbol,
            isin=inputs.get("isin"),
            investment_focus=getattr(p, "investment_focus", None) or inputs.get("investment_focus"),
            index_tracked=inputs.get("index_tracked"),
            category=(meta.category if meta else None) or inputs.get("category"),
            enrichment_name=inputs.get("enrichment_name"),
        )
        if asset_class == "unknown":
            unknown_symbols.append(p.symbol)
        dividend_yield = meta.dividend_yield if meta else None
        if not dividend_yield:
            # Accumulating funds and instruments without data: no income
            # projected, listed explicitly.
            if asset_class != "cash":
                missing_yield_symbols.append(p.symbol)
            continue
        annual_div = float(p.market_value) * float(dividend_yield) / 100.0
        bucket_dividends[bucket_of_class.get(asset_class, "other_or_unknown")] += annual_div

    equity_annual_dividends = bucket_dividends["equity"]
    fixed_income_annual_dividends = bucket_dividends["fixed_income"]
    other_annual_dividends = bucket_dividends["other_or_unknown"]
    # Invariant: the buckets add up to the projected gross income.
    total_annual_dividends = equity_annual_dividends + fixed_income_annual_dividends + other_annual_dividends

    projections = []
    for years in (1, 3, 5):
        # Project dividends with differentiated growth rates
        gross_income = 0.0
        for y in range(1, years + 1):
            gross_income += (
                equity_annual_dividends * (1 + EQUITY_GROWTH_RATE) ** y
                + fixed_income_annual_dividends * (1 + FIXED_INCOME_GROWTH_RATE) ** y
                + other_annual_dividends * (1 + OTHER_GROWTH_RATE) ** y
            )

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
        "tax_note": (
            f"Aliquota uniforme del {tax_rate:g}% applicata a tutto il reddito lordo. "
            "Non è modellata l'aliquota agevolata del 12,5% sui titoli di Stato "
            "e assimilati (né la quota di titoli di Stato negli ETF obbligazionari): "
            "per la componente a reddito fisso il netto può essere sottostimato."
        ),
        "dividend_growth_equity_pct": round(EQUITY_GROWTH_RATE * 100, 1),
        "dividend_growth_fixed_income_pct": round(FIXED_INCOME_GROWTH_RATE * 100, 1),
        "dividend_growth_other_or_unknown_pct": round(OTHER_GROWTH_RATE * 100, 1),
        "growth_note": (
            "Crescita 0% sul reddito fisso, inclusi i bond indicizzati all'inflazione "
            "(ipotesi aperta, TASK-36); 0% sul bucket other_or_unknown."
        ),
        "equity_annual_dividends_eur": round(equity_annual_dividends, 2),
        "fixed_income_annual_dividends_eur": round(fixed_income_annual_dividends, 2),
        "other_or_unknown_annual_dividends_eur": round(other_annual_dividends, 2),
        "unknown_class_symbols": unknown_symbols,
        "missing_yield_symbols": missing_yield_symbols,
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
    **DOCTOR_TOOL_HANDLERS,
}
