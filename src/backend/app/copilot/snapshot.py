"""Portfolio snapshot builders for the Copilot context."""

from __future__ import annotations

from ..services.performance_service import PerformanceService
from ..repository import PortfolioRepository
from ..services.portfolio_doctor import analyze_portfolio_health, compute_weighted_ter, run_monte_carlo_projection
from ..services.portfolio_doctor._holdings import _load_holdings


# ---------------------------------------------------------------------------
# Lightweight snapshot builder (for agentic mode -- less tokens)
# ---------------------------------------------------------------------------

def build_portfolio_snapshot_light(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str,
) -> dict:
    """Build a compact snapshot for the agentic system prompt.

    Includes summary + positions + target drift so the model has enough
    context to give rich answers and decide which tools to call.
    Heavier data (doctor, monte carlo, transactions) is fetched on-demand.
    """
    summary = repo.get_summary(portfolio_id, user_id)
    positions = repo.get_positions(portfolio_id, user_id)
    allocation = repo.get_allocation(portfolio_id, user_id)

    snapshot: dict = {
        "portfolio": {
            "name": f"Portfolio #{portfolio_id}",
            "base_currency": summary.base_currency,
            "market_value": round(summary.market_value, 2),
            "cost_basis": round(summary.cost_basis, 2),
            "unrealized_pl": round(summary.unrealized_pl, 2),
            "unrealized_pl_pct": round(summary.unrealized_pl_pct, 2),
            "day_change": round(summary.day_change, 2),
            "day_change_pct": round(summary.day_change_pct, 2),
            "cash_balance": round(summary.cash_balance, 2),
        },
    }

    # Positions (top 15 by weight -- compact)
    sorted_pos = sorted(positions, key=lambda p: p.weight, reverse=True)[:15]
    snapshot["positions"] = [
        {
            "symbol": p.symbol,
            "name": p.name,
            "weight": round(p.weight, 2),
            "market_value": round(p.market_value, 2),
            "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
            "day_change_pct": round(p.day_change_pct, 2) if p.day_change_pct else 0,
        }
        for p in sorted_pos
    ]

    # Enrichment: position count and weighted TER
    snapshot["portfolio"]["total_positions"] = len(positions)
    try:
        holdings = _load_holdings(repo, portfolio_id, user_id)
        wter = compute_weighted_ter(holdings, repo)
        if wter is not None:
            snapshot["portfolio"]["weighted_ter_pct"] = round(wter, 3)
    except Exception:
        pass

    # Target drift (if targets exist)
    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
        if target_alloc:
            alloc_map = {a.asset_id: a.weight_pct for a in allocation}
            snapshot["target_drift"] = [
                {
                    "symbol": ta.symbol,
                    "current_weight": round(alloc_map.get(ta.asset_id, 0.0), 2),
                    "target_weight": round(ta.weight_pct, 2),
                    "drift": round(alloc_map.get(ta.asset_id, 0.0) - ta.weight_pct, 2),
                }
                for ta in target_alloc
            ]
    except Exception:
        pass

    # Performance summary (compact -- just TWR percentages)
    try:
        from ..services.performance_service import PerformanceService
        perf_service = PerformanceService(repo)
        perf_data = {}
        for period in ("1m", "3m", "ytd", "1y"):
            try:
                ps = perf_service.get_performance_summary(portfolio_id, user_id, period)
                perf_data[f"twr_{period}"] = round(ps.twr.twr_pct, 2) if ps.twr.twr_pct is not None else None
            except Exception:
                pass
        if perf_data:
            snapshot["performance"] = perf_data
    except Exception:
        pass

    # Resolve actual portfolio name
    try:
        portfolios = repo.list_portfolios(user_id)
        for p in portfolios:
            if p.id == portfolio_id:
                snapshot["portfolio"]["name"] = p.name
                break
    except Exception:
        pass

    # FIRE settings (if configured)
    try:
        user_settings = repo.get_user_settings(user_id)
        if user_settings.fire_annual_expenses > 0:
            swr = user_settings.fire_safe_withdrawal_rate or 4
            fire_target = user_settings.fire_annual_expenses / (swr / 100)
            coverage_pct = (summary.market_value / fire_target * 100) if fire_target > 0 else 0
            fire_data: dict = {
                "annual_expenses": user_settings.fire_annual_expenses,
                "annual_contribution": user_settings.fire_annual_contribution,
                "safe_withdrawal_rate_pct": swr,
                "capital_gains_tax_rate_pct": user_settings.fire_capital_gains_tax_rate,
                "fire_target": round(fire_target, 0),
                "coverage_pct": round(coverage_pct, 1),
            }
            if user_settings.fire_current_age:
                fire_data["current_age"] = user_settings.fire_current_age
            if user_settings.fire_target_age:
                fire_data["target_age"] = user_settings.fire_target_age
            snapshot["fire"] = fire_data
    except Exception:
        pass

    return snapshot


def build_aggregate_snapshot_light(
    repo: PortfolioRepository,
    portfolio_ids: list[int],
    user_id: str,
) -> dict:
    """Build a combined snapshot from multiple portfolios for the agentic system prompt."""
    all_positions: list[dict] = []
    total_market_value = 0.0
    total_cost_basis = 0.0
    total_unrealized_pl = 0.0
    total_day_change = 0.0
    total_cash = 0.0
    base_currency = "EUR"
    portfolio_names: list[str] = []

    try:
        portfolios = repo.list_portfolios(user_id)
        name_map = {p.id: p.name for p in portfolios}
    except Exception:
        name_map = {}

    for pid in portfolio_ids:
        try:
            s = repo.get_summary(pid, user_id)
            total_market_value += s.market_value
            total_cost_basis += s.cost_basis
            total_unrealized_pl += s.unrealized_pl
            total_day_change += s.day_change
            total_cash += s.cash_balance
            base_currency = s.base_currency
            portfolio_names.append(name_map.get(pid, f"Portfolio #{pid}"))

            positions = repo.get_positions(pid, user_id)
            for p in positions:
                all_positions.append({
                    "symbol": p.symbol,
                    "name": p.name,
                    "market_value": p.market_value,
                    "weight": p.weight,
                    "unrealized_pl_pct": p.unrealized_pl_pct,
                    "day_change_pct": p.day_change_pct or 0,
                    "portfolio": name_map.get(pid, f"#{pid}"),
                })
        except Exception:
            continue

    # Recalculate weights based on total market value
    if total_market_value > 0:
        for pos in all_positions:
            pos["weight"] = round(pos["market_value"] / total_market_value * 100, 2)

    sorted_pos = sorted(all_positions, key=lambda p: p["market_value"], reverse=True)[:20]
    for pos in sorted_pos:
        pos["market_value"] = round(pos["market_value"], 2)
        pos["unrealized_pl_pct"] = round(pos["unrealized_pl_pct"], 2)
        pos["day_change_pct"] = round(pos["day_change_pct"], 2)

    unrealized_pl_pct = (total_unrealized_pl / total_cost_basis * 100) if total_cost_basis > 0 else 0
    day_change_pct = (total_day_change / (total_market_value - total_day_change) * 100) if (total_market_value - total_day_change) > 0 else 0

    snapshot: dict = {
        "aggregate_portfolio": {
            "portfolios": portfolio_names,
            "portfolio_count": len(portfolio_ids),
            "base_currency": base_currency,
            "market_value": round(total_market_value, 2),
            "cost_basis": round(total_cost_basis, 2),
            "unrealized_pl": round(total_unrealized_pl, 2),
            "unrealized_pl_pct": round(unrealized_pl_pct, 2),
            "day_change": round(total_day_change, 2),
            "day_change_pct": round(day_change_pct, 2),
            "cash_balance": round(total_cash, 2),
        },
        "positions": sorted_pos,
    }

    # FIRE settings
    try:
        user_settings = repo.get_user_settings(user_id)
        if user_settings.fire_annual_expenses > 0:
            swr = user_settings.fire_safe_withdrawal_rate or 4
            fire_target = user_settings.fire_annual_expenses / (swr / 100)
            coverage_pct = (total_market_value / fire_target * 100) if fire_target > 0 else 0
            fire_data: dict = {
                "annual_expenses": user_settings.fire_annual_expenses,
                "annual_contribution": user_settings.fire_annual_contribution,
                "safe_withdrawal_rate_pct": swr,
                "capital_gains_tax_rate_pct": user_settings.fire_capital_gains_tax_rate,
                "fire_target": round(fire_target, 0),
                "coverage_pct": round(coverage_pct, 1),
            }
            if user_settings.fire_current_age:
                fire_data["current_age"] = user_settings.fire_current_age
            if user_settings.fire_target_age:
                fire_data["target_age"] = user_settings.fire_target_age
            snapshot["fire"] = fire_data
    except Exception:
        pass

    return snapshot


# ---------------------------------------------------------------------------
# Full snapshot builder (for non-agentic / fallback mode)
# ---------------------------------------------------------------------------

def build_portfolio_snapshot(
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> dict:
    """Build a compact JSON snapshot of the portfolio for the LLM context."""
    summary = repo.get_summary(portfolio_id, user_id)
    positions = repo.get_positions(portfolio_id, user_id)
    allocation = repo.get_allocation(portfolio_id, user_id)

    # Target allocation (may not exist)
    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    except Exception:
        target_alloc = []

    # Best/worst performers
    try:
        target_perf = repo.get_portfolio_target_performance(portfolio_id, user_id)
        best = {"symbol": target_perf.best.symbol, "day_change_pct": target_perf.best.day_change_pct} if target_perf.best else None
        worst = {"symbol": target_perf.worst.symbol, "day_change_pct": target_perf.worst.day_change_pct} if target_perf.worst else None
    except Exception:
        best = worst = None

    # Performance summary
    perf_data = {}
    for period in ("1m", "3m", "ytd", "1y"):
        try:
            ps = perf_service.get_performance_summary(portfolio_id, user_id, period)
            perf_data[f"twr_{period}"] = round(ps.twr.twr_pct, 2) if ps.twr.twr_pct is not None else None
        except Exception:
            pass

    # Limit positions to top 30 by weight
    sorted_positions = sorted(positions, key=lambda p: p.weight, reverse=True)[:30]
    pos_list = [
        {
            "symbol": p.symbol,
            "name": p.name,
            "weight": round(p.weight, 2),
            "market_value": round(p.market_value, 2),
            "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
            "day_change_pct": round(p.day_change_pct, 2) if p.day_change_pct else 0,
        }
        for p in sorted_positions
    ]

    # Target drift
    alloc_map = {a.asset_id: a.weight_pct for a in allocation}
    drift_list = []
    for ta in target_alloc:
        current = alloc_map.get(ta.asset_id, 0.0)
        drift_list.append({
            "symbol": ta.symbol,
            "current_weight": round(current, 2),
            "target_weight": round(ta.weight_pct, 2),
            "drift": round(current - ta.weight_pct, 2),
        })

    snapshot = {
        "portfolio": {
            "name": f"Portfolio #{portfolio_id}",
            "base_currency": summary.base_currency,
            "market_value": round(summary.market_value, 2),
            "cost_basis": round(summary.cost_basis, 2),
            "unrealized_pl": round(summary.unrealized_pl, 2),
            "unrealized_pl_pct": round(summary.unrealized_pl_pct, 2),
            "day_change": round(summary.day_change, 2),
            "day_change_pct": round(summary.day_change_pct, 2),
            "cash_balance": round(summary.cash_balance, 2),
        },
        "positions": pos_list,
        "performance": perf_data,
    }

    try:
        doctor = analyze_portfolio_health(repo, portfolio_id, user_id)
        snapshot["doctor"] = {
            "score": doctor.score,
            "risk_level": doctor.summary.risk_level,
            "diversification": doctor.summary.diversification,
            "overlap": doctor.summary.overlap,
            "cost_efficiency": doctor.summary.cost_efficiency,
            "max_position_weight": round(doctor.metrics.max_position_weight, 2),
            "overlap_score": round(doctor.metrics.overlap_score, 2),
            "portfolio_volatility": round(doctor.metrics.portfolio_volatility, 2) if doctor.metrics.portfolio_volatility is not None else None,
            "weighted_ter": round(doctor.metrics.weighted_ter, 2) if doctor.metrics.weighted_ter is not None else None,
            "top_alerts": [alert.message for alert in doctor.alerts[:5]],
            "top_suggestions": [suggestion.message for suggestion in doctor.suggestions[:5]],
        }
    except Exception:
        pass

    try:
        monte_carlo = run_monte_carlo_projection(repo, portfolio_id, user_id)
        snapshot["doctor_monte_carlo"] = {
            "annualized_mean_return_pct": round(monte_carlo.annualized_mean_return_pct, 2),
            "annualized_volatility_pct": round(monte_carlo.annualized_volatility_pct, 2),
            "horizons": monte_carlo.horizons,
            "projections": [
                {
                    "year": projection.year,
                    "p25": projection.p25,
                    "p50": projection.p50,
                    "p75": projection.p75,
                }
                for projection in monte_carlo.projections[:10]
                if projection.year > 0
            ],
        }
    except Exception:
        pass

    if drift_list:
        snapshot["target_drift"] = drift_list
    if best:
        snapshot["best_performer"] = best
    if worst:
        snapshot["worst_performer"] = worst

    # Replace portfolio name with actual name
    try:
        portfolios = repo.list_portfolios(user_id)
        for p in portfolios:
            if p.id == portfolio_id:
                snapshot["portfolio"]["name"] = p.name
                break
    except Exception:
        pass

    return snapshot
