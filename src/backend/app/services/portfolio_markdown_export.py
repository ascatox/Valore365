"""Render a portfolio snapshot as Markdown, meant to be pasted into an
external AI assistant (ChatGPT, Claude, Gemini, ...)."""

from __future__ import annotations

from datetime import date

from collections.abc import Sequence

from ..copilot.snapshot import build_portfolio_snapshot, doctor_snapshot, monte_carlo_snapshot
from ..repository import PortfolioRepository, normalize_portfolio_ids
from .performance_service import PerformanceService
from .portfolio_doctor import analyze_portfolio_health, compute_weighted_ter, run_monte_carlo_projection
from .portfolio_doctor._holdings import _load_holdings

_PERF_PERIODS = ("1m", "3m", "6m", "ytd", "1y", "all")


def _num(value: object, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/D"
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}{suffix}".replace(",", " ")
    return f"{value}{suffix}"


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _collect_performance_rows(
    perf_service: PerformanceService,
    portfolio_id: int | Sequence[int],
    user_id: str,
) -> list[list[str]]:
    rows: list[list[str]] = []
    for period in _PERF_PERIODS:
        try:
            ps = perf_service.get_performance_summary(portfolio_id, user_id, period)
        except Exception:
            continue
        rows.append([
            ps.period_label,
            _num(ps.twr.twr_pct, suffix="%"),
            _num(ps.mwr.mwr_pct, suffix="%"),
            _num(ps.twr.twr_annualized_pct, suffix="%"),
            _num(ps.mwr.mwr_annualized_pct, suffix="%"),
            _num(ps.initial_value),
            _num(ps.net_invested),
            _num(ps.absolute_gain),
        ])
    return rows


def build_portfolio_markdown(
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> str:
    snapshot = build_portfolio_snapshot(repo, perf_service, portfolio_id, user_id)
    performance_rows = _collect_performance_rows(perf_service, portfolio_id, user_id)
    return render_snapshot_markdown(snapshot, portfolio_id, performance_rows)


# Sections of the single export that depend on per-portfolio settings and have
# no aggregate equivalent: listed in the aggregate document instead of shown.
AGGREGATE_OMITTED_SECTIONS = (
    "scostamento dai target di allocazione (i target sono definiti per singolo portafoglio)",
    "piani di accumulo (PAC) ed esecuzioni in attesa (gestiti per singolo portafoglio)",
)


def build_aggregate_portfolio_snapshot(
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_ids: Sequence[int],
    user_id: str,
) -> dict:
    """Snapshot of several portfolios read as one (vista aggregata).

    Same shape as ``build_portfolio_snapshot`` over the merged data of the
    aggregate repository/Doctor reads, plus an ``aggregate`` entry with the
    included portfolio names. Target drift and PAC plans are per portfolio and
    are left out. Scope errors (empty, not owned, mixed currencies) propagate
    as ValueError from the first read.
    """
    ids = normalize_portfolio_ids(portfolio_ids)
    summary = repo.get_summary_multi(ids, user_id)
    positions = repo.get_positions_multi(ids, user_id)

    try:
        name_map = {p.id: p.name for p in repo.list_portfolios(user_id)}
    except Exception:
        name_map = {}
    names = [name_map.get(pid, f"Portfolio #{pid}") for pid in ids]

    portfolio: dict = {
        "name": "Vista aggregata",
        "base_currency": summary.base_currency,
        "market_value": round(summary.market_value, 2),
        "cost_basis": round(summary.cost_basis, 2),
        "unrealized_pl": round(summary.unrealized_pl, 2),
        "unrealized_pl_pct": round(summary.unrealized_pl_pct, 2),
        "day_change": round(summary.day_change, 2),
        "day_change_pct": round(summary.day_change_pct, 2),
        "cash_balance": round(summary.cash_balance, 2),
        "total_positions": len(positions),
    }
    try:
        wter = compute_weighted_ter(_load_holdings(repo, ids, user_id), repo)
        if wter is not None:
            portfolio["weighted_ter_pct"] = round(wter, 3)
    except Exception:
        pass

    sorted_positions = sorted(positions, key=lambda p: p.weight, reverse=True)[:30]
    snapshot: dict = {
        "portfolio": portfolio,
        "aggregate": {"portfolio_ids": ids, "portfolios": names},
        "positions": [
            {
                "symbol": p.symbol,
                "name": p.name,
                "weight": round(p.weight, 2),
                "market_value": round(p.market_value, 2),
                "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
                "day_change_pct": round(p.day_change_pct, 2) if p.day_change_pct else 0,
            }
            for p in sorted_positions
        ],
    }

    try:
        snapshot["doctor"] = doctor_snapshot(analyze_portfolio_health(repo, ids, user_id))
    except Exception:
        pass
    try:
        snapshot["doctor_monte_carlo"] = monte_carlo_snapshot(run_monte_carlo_projection(repo, ids, user_id))
    except Exception:
        pass

    # Best/worst of the day from the merged positions (the single export reads
    # them from the per-portfolio target performance).
    movers = [p for p in positions if p.day_change_pct is not None]
    if movers:
        best = max(movers, key=lambda p: p.day_change_pct)
        worst = min(movers, key=lambda p: p.day_change_pct)
        snapshot["best_performer"] = {"symbol": best.symbol, "day_change_pct": round(best.day_change_pct, 2)}
        if worst.asset_id != best.asset_id:
            snapshot["worst_performer"] = {"symbol": worst.symbol, "day_change_pct": round(worst.day_change_pct, 2)}

    return snapshot


def build_aggregate_portfolio_markdown(
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_ids: Sequence[int],
    user_id: str,
) -> str:
    snapshot = build_aggregate_portfolio_snapshot(repo, perf_service, portfolio_ids, user_id)
    ids = snapshot["aggregate"]["portfolio_ids"]
    performance_rows = _collect_performance_rows(perf_service, ids, user_id)
    return render_snapshot_markdown(snapshot, 0, performance_rows)


def render_snapshot_markdown(
    snapshot: dict,
    portfolio_id: int,
    performance_rows: list[list[str]] | None = None,
) -> str:
    portfolio = snapshot.get("portfolio", {})
    name = portfolio.get("name", f"Portfolio #{portfolio_id}")
    currency = portfolio.get("base_currency", "")

    aggregate = snapshot.get("aggregate")

    lines: list[str] = []
    if aggregate:
        lines.append("# Vista aggregata — Snapshot portafogli")
        lines.append("")
        lines.append(f"Vista aggregata: {', '.join(aggregate.get('portfolios') or [])}")
        lines.append("")
        lines.append(
            "I portafogli elencati sono letti come uno solo: posizioni sullo stesso strumento sommate, "
            "pesi ricalcolati sul totale, performance calcolate sui flussi combinati."
        )
        lines.append("")
    else:
        lines.append(f"# {name} — Snapshot portafoglio")
        lines.append("")
    lines.append(
        f"Snapshot generato da Valore365 il {date.today().isoformat()}."
        + (f" Valori monetari in {currency}, salvo dove indicato diversamente." if currency else "")
    )

    # --- Riepilogo ---
    lines.append("")
    lines.append("## Riepilogo")
    lines.append("")
    summary_rows = [
        ["Valore di mercato", _num(portfolio.get("market_value"))],
        ["Costo di carico", _num(portfolio.get("cost_basis"))],
        ["P/L non realizzato", f"{_num(portfolio.get('unrealized_pl'))} ({_num(portfolio.get('unrealized_pl_pct'), suffix='%')})"],
        ["Variazione giornaliera", f"{_num(portfolio.get('day_change'))} ({_num(portfolio.get('day_change_pct'), suffix='%')})"],
        ["Liquidità", _num(portfolio.get("cash_balance"))],
    ]
    if portfolio.get("total_positions") is not None:
        summary_rows.append(["Numero posizioni", str(portfolio["total_positions"])])
    if portfolio.get("weighted_ter_pct") is not None:
        summary_rows.append(["TER medio ponderato", _num(portfolio["weighted_ter_pct"], 3, "%")])
    lines.extend(_md_table(["Voce", "Valore"], summary_rows))

    # --- Posizioni ---
    positions = snapshot.get("positions") or []
    if positions:
        lines.append("")
        lines.append("## Posizioni principali")
        lines.append("")
        lines.append(
            "P/L su costo medio: variazione del valore attuale rispetto al prezzo medio di carico "
            "(commissioni incluse, convertito in valuta del portafoglio). Non include dividendi o "
            "altre distribuzioni incassate, quindi non è il rendimento totale dello strumento."
        )
        lines.append("")
        lines.extend(_md_table(
            ["Simbolo", "Nome", "Peso", "Valore", "P/L su costo medio", "Var. giorno"],
            [
                [
                    str(p.get("symbol", "")),
                    str(p.get("name", "")),
                    _num(p.get("weight"), suffix="%"),
                    _num(p.get("market_value")),
                    _num(p.get("unrealized_pl_pct"), suffix="%"),
                    _num(p.get("day_change_pct"), suffix="%"),
                ]
                for p in positions
            ],
        ))

    # --- Performance ---
    if performance_rows:
        lines.append("")
        lines.append("## Performance")
        lines.append("")
        lines.append(
            "TWR e MWR sono rendimenti di periodo; le colonne annualizzate "
            "sono valorizzate solo per periodi di almeno un anno."
        )
        lines.append("")
        lines.append(
            "N/D = dato non calcolabile (ad esempio valore iniziale o quotazioni assenti, oppure MWR "
            "non convergente), non zero. "
            "Guadagno assoluto = valore finale (liquidità inclusa) - valore iniziale - netto investito "
            "(versamenti meno prelievi del periodo). Il valore iniziale è quello a fine giornata "
            "precedente all'inizio del periodo: 0 se il periodo parte dal primo movimento."
        )
        lines.append("")
        lines.extend(_md_table(
            ["Periodo", "TWR", "MWR", "TWR ann.", "MWR ann.", "Valore iniziale", "Netto investito", "Guadagno assoluto"],
            performance_rows,
        ))
    elif snapshot.get("performance"):
        lines.append("")
        lines.append("## Performance (TWR di periodo)")
        lines.append("")
        lines.extend(_md_table(
            ["Periodo", "TWR"],
            [[k.removeprefix("twr_"), _num(v, suffix="%")] for k, v in snapshot["performance"].items()],
        ))

    # --- Salute del portafoglio (Doctor) ---
    doctor = snapshot.get("doctor")
    if doctor:
        lines.append("")
        lines.append("## Salute del portafoglio")
        lines.append("")
        doctor_rows = [
            ["Punteggio", _num(doctor.get("score"), 0)],
            ["Livello di rischio", str(doctor.get("risk_level", "N/D"))],
            ["Diversificazione", str(doctor.get("diversification", "N/D"))],
            ["Sovrapposizione", str(doctor.get("overlap", "N/D"))],
            ["Efficienza dei costi", str(doctor.get("cost_efficiency", "N/D"))],
            ["Peso massimo posizione (fondi/ETF inclusi)", _num(doctor.get("max_position_weight"), suffix="%")],
            ["Peso massimo titolo singolo (esclusi fondi/ETF)", _num(doctor.get("max_single_security_weight"), suffix="%")],
            ["Sovrapposizione stimata (euristica per tipo, indici e regione)", _num(doctor.get("overlap_score"), suffix="%")],
            [
                "Volatilità stimata (media ponderata delle volatilità storiche dei singoli strumenti, ~12 mesi, senza correlazioni)",
                _num(doctor.get("portfolio_volatility"), suffix="%"),
            ],
            ["TER medio ponderato", _num(doctor.get("weighted_ter"), suffix="%")],
        ]
        lines.extend(_md_table(["Metrica", "Valore"], doctor_rows))
        if doctor.get("top_alerts"):
            lines.append("")
            lines.append("### Alert principali")
            lines.append("")
            lines.extend(f"- {alert}" for alert in doctor["top_alerts"])
        if doctor.get("top_suggestions"):
            lines.append("")
            lines.append("### Suggerimenti")
            lines.append("")
            lines.extend(f"- {suggestion}" for suggestion in doctor["top_suggestions"])

    # --- Monte Carlo ---
    monte_carlo = snapshot.get("doctor_monte_carlo")
    if monte_carlo:
        lines.append("")
        lines.append("## Proiezione Monte Carlo")
        lines.append("")
        lines.append(
            f"Rendimento atteso di lungo periodo (ipotesi per classe di attivo): {_num(monte_carlo.get('annualized_mean_return_pct'), suffix='%')}, "
            f"volatilità annualizzata: {_num(monte_carlo.get('annualized_volatility_pct'), suffix='%')} "
            "(la maggiore tra la volatilità realizzata del portafoglio negli ultimi ~12 mesi e quella di lungo periodo "
            "ipotizzata per la sua composizione per classi di attivo: non è la stessa stima della volatilità della salute del portafoglio)."
        )
        lines.append("")
        lines.append(
            "I valori di percentile sono indici base 100 (valore di partenza = 100), non importi in valuta: "
            "es. 106 = +6% rispetto al valore di partenza, al netto di versamenti e prelievi (assenti nella simulazione)."
        )
        projections = monte_carlo.get("projections") or []
        if projections:
            lines.append("")
            lines.extend(_md_table(
                ["Anno", "P25 (indice)", "Mediana P50 (indice)", "P75 (indice)"],
                [
                    [str(pr.get("year")), _num(pr.get("p25"), 0), _num(pr.get("p50"), 0), _num(pr.get("p75"), 0)]
                    for pr in projections
                ],
            ))

    # --- Target drift ---
    target_drift = snapshot.get("target_drift") or []
    if target_drift:
        lines.append("")
        lines.append("## Scostamento dai target di allocazione")
        lines.append("")
        lines.extend(_md_table(
            ["Simbolo", "Peso attuale", "Peso target", "Drift"],
            [
                [
                    str(t.get("symbol", "")),
                    _num(t.get("current_weight"), suffix="%"),
                    _num(t.get("target_weight"), suffix="%"),
                    _num(t.get("drift"), suffix="%"),
                ]
                for t in target_drift
            ],
        ))

    # --- Best / worst performer ---
    best = snapshot.get("best_performer")
    worst = snapshot.get("worst_performer")
    if best or worst:
        lines.append("")
        lines.append("## Migliore e peggiore di giornata")
        lines.append("")
        if best:
            lines.append(f"- Migliore: {best.get('symbol')} ({_num(best.get('day_change_pct'), suffix='%')})")
        if worst:
            lines.append(f"- Peggiore: {worst.get('symbol')} ({_num(worst.get('day_change_pct'), suffix='%')})")

    # --- Piani PAC ---
    pac = snapshot.get("pac_plans")
    if pac and pac.get("active_rules"):
        lines.append("")
        lines.append("## Piani di accumulo (PAC) attivi")
        lines.append("")
        lines.extend(_md_table(
            ["Simbolo", "Nome", "Modalità", "Importo", "Quantità", "Frequenza", "Inizio", "Fine"],
            [
                [
                    str(r.get("symbol", "")),
                    str(r.get("asset_name", "")),
                    str(r.get("mode", "")),
                    _num(r.get("amount")),
                    _num(r.get("quantity"), 4),
                    str(r.get("frequency", "")),
                    str(r.get("start_date", "")),
                    str(r.get("end_date") or "-"),
                ]
                for r in pac["active_rules"]
            ],
        ))
        lines.append("")
        lines.append(f"Esecuzioni PAC in attesa: {pac.get('pending_executions_count', 0)}")

    if aggregate:
        lines.append("")
        lines.append("## Non inclusi nella vista aggregata")
        lines.append("")
        lines.extend(f"- {section}" for section in AGGREGATE_OMITTED_SECTIONS)

    lines.append("")
    return "\n".join(lines)
