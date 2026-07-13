"""Render a portfolio snapshot as Markdown, meant to be pasted into an
external AI assistant (ChatGPT, Claude, Gemini, ...)."""

from __future__ import annotations

from datetime import date

from ..copilot.snapshot import build_portfolio_snapshot
from ..repository import PortfolioRepository
from .performance_service import PerformanceService

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
    portfolio_id: int,
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


def render_snapshot_markdown(
    snapshot: dict,
    portfolio_id: int,
    performance_rows: list[list[str]] | None = None,
) -> str:
    portfolio = snapshot.get("portfolio", {})
    name = portfolio.get("name", f"Portfolio #{portfolio_id}")
    currency = portfolio.get("base_currency", "")

    lines: list[str] = []
    lines.append(f"# {name} — Snapshot portafoglio")
    lines.append("")
    lines.append(
        f"Snapshot generato da Valore365 il {date.today().isoformat()}."
        + (f" Valori monetari in {currency}." if currency else "")
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
        lines.extend(_md_table(
            ["Simbolo", "Nome", "Peso", "Valore", "P/L", "Var. giorno"],
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
        lines.extend(_md_table(
            ["Periodo", "TWR", "MWR", "TWR ann.", "MWR ann.", "Netto investito", "Guadagno assoluto"],
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
            ["Peso massimo posizione", _num(doctor.get("max_position_weight"), suffix="%")],
            ["Volatilità stimata", _num(doctor.get("portfolio_volatility"), suffix="%")],
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
            f"Rendimento medio annualizzato: {_num(monte_carlo.get('annualized_mean_return_pct'), suffix='%')}, "
            f"volatilità annualizzata: {_num(monte_carlo.get('annualized_volatility_pct'), suffix='%')}."
        )
        projections = monte_carlo.get("projections") or []
        if projections:
            lines.append("")
            lines.extend(_md_table(
                ["Anno", "P25", "Mediana (P50)", "P75"],
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

    lines.append("")
    return "\n".join(lines)
