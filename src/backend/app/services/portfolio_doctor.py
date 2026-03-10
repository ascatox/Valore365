import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text

from ..repository import PortfolioRepository
from ..schemas.portfolio_doctor import (
    DecumulationPlanResponse,
    DecumulationYearProjection,
    MonteCarloProjectionResponse,
    MonteCarloYearProjection,
    PortfolioHealthAlert,
    PortfolioHealthCategoryScores,
    PortfolioHealthMetrics,
    PortfolioHealthResponse,
    PortfolioHealthSuggestion,
    PortfolioHealthSummary,
)


REGIONS = ("usa", "europe", "emerging", "other")
GLOBAL_EQUITY_SPLIT = {"usa": 55.0, "europe": 20.0, "emerging": 10.0, "other": 15.0}
GLOBAL_BOND_SPLIT = {"usa": 40.0, "europe": 30.0, "emerging": 5.0, "other": 25.0}
EUROPE_SUFFIXES = (".MI", ".PA", ".AS", ".DE", ".L", ".SW", ".MC", ".BR")
EMERGING_CURRENCIES = {"CNY", "CNH", "INR", "BRL", "MXN", "ZAR", "TWD", "KRW", "IDR", "THB"}
EUROPE_CURRENCIES = {"EUR", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF"}


@dataclass
class AnalyzedHolding:
    asset_id: int
    symbol: str
    name: str
    asset_type: str
    quote_currency: str
    market_value: float
    weight_pct: float


def analyze_portfolio_health(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str | None = None,
) -> PortfolioHealthResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    holdings = _load_holdings(repo, portfolio_id, user_id)
    if not holdings:
        return empty_health_response(portfolio_id)

    geographic_exposure = compute_geographic_exposure(holdings)
    max_position_weight = compute_max_position_weight(holdings)
    overlap_score = compute_overlap_score(holdings)
    portfolio_volatility = compute_portfolio_volatility(repo, holdings)
    weighted_ter = compute_weighted_ter(holdings)
    top3_weight = round(sum(h.weight_pct for h in holdings[:3]), 2)
    equity_weight = round(sum(h.weight_pct for h in holdings if _is_equity_like(h)), 2)

    metrics = PortfolioHealthMetrics(
        geographic_exposure=geographic_exposure,
        max_position_weight=max_position_weight,
        overlap_score=overlap_score,
        portfolio_volatility=portfolio_volatility,
        weighted_ter=weighted_ter,
    )
    category_scores = compute_category_scores(metrics, top3_weight=top3_weight, equity_weight=equity_weight)
    score = compute_total_score(category_scores)
    summary = build_summary(metrics, category_scores)
    alerts = build_alerts(metrics, holdings)
    suggestions = build_suggestions(metrics, equity_weight=equity_weight)

    return PortfolioHealthResponse(
        portfolio_id=portfolio_id,
        score=score,
        summary=summary,
        metrics=metrics,
        category_scores=category_scores,
        alerts=alerts,
        suggestions=suggestions,
    )


def empty_health_response(portfolio_id: int) -> PortfolioHealthResponse:
    return PortfolioHealthResponse(
        portfolio_id=portfolio_id,
        score=0,
        summary=PortfolioHealthSummary(
            risk_level="unknown",
            diversification="unknown",
            overlap="unknown",
            cost_efficiency="unknown",
        ),
        metrics=PortfolioHealthMetrics(
            geographic_exposure={},
            max_position_weight=0,
            overlap_score=0,
            portfolio_volatility=None,
            weighted_ter=None,
        ),
        category_scores=PortfolioHealthCategoryScores(
            diversification=0,
            risk=0,
            concentration=0,
            overlap=0,
            cost_efficiency=0,
        ),
        alerts=[],
        suggestions=[],
    )


def _load_holdings(repo: PortfolioRepository, portfolio_id: int, user_id: str) -> list[AnalyzedHolding]:
    positions = repo.get_positions(portfolio_id, user_id)
    if not positions:
        return []

    asset_ids = [position.asset_id for position in positions]
    with repo.engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                select id, asset_type, quote_currency
                from assets
                where id = any(:asset_ids)
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()

    meta_by_asset = {
        int(row["id"]): {
            "asset_type": str(row["asset_type"] or ""),
            "quote_currency": str(row["quote_currency"] or ""),
        }
        for row in rows
    }

    holdings: list[AnalyzedHolding] = []
    for position in positions:
        meta = meta_by_asset.get(position.asset_id, {})
        holdings.append(
            AnalyzedHolding(
                asset_id=position.asset_id,
                symbol=position.symbol,
                name=position.name,
                asset_type=str(meta.get("asset_type") or "stock"),
                quote_currency=str(meta.get("quote_currency") or ""),
                market_value=float(position.market_value),
                weight_pct=float(position.weight),
            )
        )
    return holdings


def compute_geographic_exposure(holdings: list[AnalyzedHolding]) -> dict[str, float]:
    exposure = {region: 0.0 for region in REGIONS}
    for holding in holdings:
        profile = infer_region_profile(holding)
        for region, split in profile.items():
            exposure[region] += holding.weight_pct * (split / 100.0)

    normalized = {region: round(max(0.0, value), 1) for region, value in exposure.items() if value > 0}
    total = round(sum(normalized.values()), 1)
    if total and total != 100.0:
        diff = round(100.0 - total, 1)
        normalized["other"] = round(normalized.get("other", 0.0) + diff, 1)
    return normalized


def infer_region_profile(holding: AnalyzedHolding) -> dict[str, float]:
    descriptor = f"{holding.symbol} {holding.name}".upper()
    asset_type = holding.asset_type.lower()

    if asset_type == "cash":
        return {"other": 100.0}
    if any(token in descriptor for token in ("EMERGING", "EM IMI", "FTSE EM", "MSCI EM", "EMIM", "EIMI")):
        return {"emerging": 100.0}
    if any(token in descriptor for token in ("EUROPE", "STOXX", "EU600", "DAX", "FTSE 100", "EURO STOXX")):
        return {"europe": 100.0}
    if any(
        token in descriptor
        for token in ("S&P 500", "SP500", "NASDAQ", "RUSSELL 1000", "RUSSELL 3000", "TOTAL MARKET", "USA", "US ")
    ):
        return {"usa": 100.0}
    if any(token in descriptor for token in ("ALL-WORLD", "ALL WORLD", "ACWI", "WORLD", "VWCE", "IWDA", "SWDA", "GLOBAL")):
        return GLOBAL_BOND_SPLIT.copy() if asset_type == "bond" else GLOBAL_EQUITY_SPLIT.copy()
    if any(holding.symbol.upper().endswith(suffix) for suffix in EUROPE_SUFFIXES):
        return {"europe": 100.0}
    if holding.quote_currency in EMERGING_CURRENCIES:
        return {"emerging": 100.0}
    if holding.quote_currency in EUROPE_CURRENCIES:
        return {"europe": 100.0}
    if holding.quote_currency == "USD":
        return {"usa": 100.0}
    return {"other": 100.0}


def compute_max_position_weight(holdings: list[AnalyzedHolding]) -> float:
    if not holdings:
        return 0.0
    return round(max(holding.weight_pct for holding in holdings), 1)


def compute_overlap_score(holdings: list[AnalyzedHolding]) -> float:
    pair_weight_total = 0.0
    weighted_overlap = 0.0
    for index, left in enumerate(holdings):
        for right in holdings[index + 1 :]:
            pair_weight = (left.weight_pct / 100.0) * (right.weight_pct / 100.0)
            if pair_weight <= 0:
                continue
            pair_overlap = estimate_overlap_between_assets(left, right)
            pair_weight_total += pair_weight
            weighted_overlap += pair_overlap * pair_weight
    if pair_weight_total == 0:
        return 0.0
    return round(max(0.0, min(100.0, weighted_overlap / pair_weight_total)), 1)


def estimate_overlap_between_assets(asset_a: AnalyzedHolding, asset_b: AnalyzedHolding) -> float:
    if asset_a.asset_type == "cash" or asset_b.asset_type == "cash":
        return 0.0
    if asset_a.asset_type == "bond" and asset_b.asset_type == "bond":
        if infer_region_profile(asset_a) == infer_region_profile(asset_b):
            return 55.0
        return 25.0
    if {asset_a.asset_type, asset_b.asset_type} == {"bond", "stock"}:
        return 5.0
    if "bond" in {asset_a.asset_type, asset_b.asset_type}:
        return 10.0

    tags_a = extract_overlap_tags(asset_a)
    tags_b = extract_overlap_tags(asset_b)
    if asset_a.symbol.upper() == asset_b.symbol.upper():
        return 100.0
    if tags_a & tags_b:
        if "broad_us_equity" in tags_a & tags_b or "global_equity" in tags_a & tags_b:
            return 85.0
        return 75.0
    if {"global_equity", "broad_us_equity"} <= (tags_a | tags_b):
        return 68.0
    if {"msci_world", "sp500"} <= (tags_a | tags_b):
        return 72.0
    if {"acwi", "sp500"} <= (tags_a | tags_b):
        return 66.0
    if {"nasdaq100", "sp500"} <= (tags_a | tags_b):
        return 55.0
    if {"global_equity", "nasdaq100"} <= (tags_a | tags_b):
        return 48.0
    region_a = dominant_region(asset_a)
    region_b = dominant_region(asset_b)
    if region_a == region_b and region_a in {"usa", "europe", "emerging"}:
        return 28.0
    if _is_equity_like(asset_a) and _is_equity_like(asset_b):
        return 18.0
    return 8.0


def extract_overlap_tags(holding: AnalyzedHolding) -> set[str]:
    descriptor = f"{holding.symbol} {holding.name}".upper()
    tags: set[str] = set()
    if any(token in descriptor for token in ("ALL-WORLD", "ALL WORLD", "ACWI", "VWCE")):
        tags.add("acwi")
        tags.add("global_equity")
    if any(token in descriptor for token in ("WORLD", "IWDA", "SWDA", "MSCI WORLD")):
        tags.add("msci_world")
        tags.add("global_equity")
    if any(token in descriptor for token in ("S&P 500", "SP500", "CSPX", "VUAA", "VUSA", "IVV", "VOO")):
        tags.add("sp500")
        tags.add("broad_us_equity")
    if any(token in descriptor for token in ("NASDAQ", "QQQ", "EQQQ", "CNDX")):
        tags.add("nasdaq100")
        tags.add("broad_us_equity")
    if any(token in descriptor for token in ("TOTAL MARKET", "VTI", "ITOT", "RUSSELL 3000")):
        tags.add("total_us_market")
        tags.add("broad_us_equity")
    if any(token in descriptor for token in ("EMERGING", "EMIM", "EIMI", "MSCI EM")):
        tags.add("emerging_equity")
    if any(token in descriptor for token in ("EUROPE", "STOXX", "EXSA", "VGK")):
        tags.add("europe_equity")
    if "TECH" in descriptor:
        tags.add("tech")
    if holding.asset_type in {"stock", "etf", "fund"}:
        tags.add("equity_like")
    return tags


def dominant_region(holding: AnalyzedHolding) -> str:
    profile = infer_region_profile(holding)
    return max(profile.items(), key=lambda item: item[1])[0]


def compute_portfolio_volatility(repo: PortfolioRepository, holdings: list[AnalyzedHolding]) -> float | None:
    asset_ids = [holding.asset_id for holding in holdings if holding.asset_type != "cash"]
    if not asset_ids:
        return None

    start_date = date.today() - timedelta(days=370)
    with repo.engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                select asset_id, price_date, close::float8 as close
                from price_bars_1d
                where asset_id = any(:asset_ids)
                  and price_date >= :start_date
                order by asset_id asc, price_date asc
                """
            ),
            {"asset_ids": asset_ids, "start_date": start_date},
        ).mappings().all()

    prices_by_asset: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        close = float(row["close"])
        if close > 0 and math.isfinite(close):
            prices_by_asset[int(row["asset_id"])].append(close)

    weighted_volatility = 0.0
    covered_weight = 0.0
    for holding in holdings:
        series = prices_by_asset.get(holding.asset_id, [])
        if len(series) < 20:
            continue
        returns = [(curr / prev) - 1.0 for prev, curr in zip(series, series[1:]) if prev > 0 and curr > 0]
        if len(returns) < 20:
            continue
        daily_volatility = statistics.pstdev(returns)
        annualized = daily_volatility * math.sqrt(252) * 100.0
        weight_fraction = holding.weight_pct / 100.0
        weighted_volatility += annualized * weight_fraction
        covered_weight += weight_fraction

    if covered_weight == 0:
        return None
    return round(weighted_volatility / covered_weight, 1)


def compute_weighted_ter(holdings: list[AnalyzedHolding]) -> float | None:
    weighted_cost = 0.0
    covered_weight = 0.0
    for holding in holdings:
        ter = infer_ter(holding)
        if ter is None:
            continue
        weight_fraction = holding.weight_pct / 100.0
        weighted_cost += ter * weight_fraction
        covered_weight += weight_fraction
    if covered_weight == 0:
        return None
    return round(weighted_cost / covered_weight, 2)


def infer_ter(holding: AnalyzedHolding) -> float | None:
    asset_type = holding.asset_type.lower()
    if asset_type in {"stock", "bond", "cash"}:
        return 0.0
    if asset_type not in {"etf", "fund"}:
        return None

    descriptor = f"{holding.symbol} {holding.name}".upper()
    if any(token in descriptor for token in ("CORE", "PRIME")):
        return 0.07
    if any(token in descriptor for token in ("S&P 500", "SP500", "VUAA", "VUSA", "CSPX", "IVV", "VOO")):
        return 0.08
    if any(token in descriptor for token in ("NASDAQ", "QQQ", "EQQQ", "CNDX")):
        return 0.2
    if any(token in descriptor for token in ("WORLD", "IWDA", "SWDA")):
        return 0.2
    if any(token in descriptor for token in ("ALL-WORLD", "ALL WORLD", "ACWI", "VWCE")):
        return 0.22
    if any(token in descriptor for token in ("EMERGING", "MSCI EM", "EIMI", "EMIM")):
        return 0.22
    if any(token in descriptor for token in ("AGGREGATE BOND", "TREASURY", "CORP BOND")):
        return 0.15
    if any(token in descriptor for token in ("VANGUARD", "ISHARES", "SPDR", "XTRACKERS", "AMUNDI", "INVESCO")):
        return 0.25
    return None


def compute_category_scores(
    metrics: PortfolioHealthMetrics,
    *,
    top3_weight: float,
    equity_weight: float,
) -> PortfolioHealthCategoryScores:
    usa = metrics.geographic_exposure.get("usa", 0.0)
    emerging = metrics.geographic_exposure.get("emerging", 0.0)

    diversification = 25
    if usa > 60:
        diversification -= 6
    if metrics.max_position_weight > 40:
        diversification -= 4
    if metrics.overlap_score > 50:
        diversification -= 4
    if emerging < 5 and equity_weight >= 60:
        diversification -= 3

    risk = 25
    if metrics.portfolio_volatility is not None:
        if metrics.portfolio_volatility > 15:
            risk -= 10
        elif metrics.portfolio_volatility >= 12:
            risk -= 5
    if metrics.max_position_weight > 40:
        risk -= 5

    concentration = 20
    if metrics.max_position_weight > 60:
        concentration -= 10
    elif metrics.max_position_weight > 40:
        concentration -= 6
    if top3_weight > 75:
        concentration -= 4

    overlap = 15
    if metrics.overlap_score > 70:
        overlap -= 12
    elif metrics.overlap_score > 50:
        overlap -= 8
    elif metrics.overlap_score > 40:
        overlap -= 4

    cost_efficiency = 15
    if metrics.weighted_ter is not None:
        if metrics.weighted_ter > 0.75:
            cost_efficiency -= 10
        elif metrics.weighted_ter > 0.5:
            cost_efficiency -= 7
        elif metrics.weighted_ter > 0.3:
            cost_efficiency -= 3

    return PortfolioHealthCategoryScores(
        diversification=max(0, min(25, diversification)),
        risk=max(0, min(25, risk)),
        concentration=max(0, min(20, concentration)),
        overlap=max(0, min(15, overlap)),
        cost_efficiency=max(0, min(15, cost_efficiency)),
    )


def build_alerts(metrics: PortfolioHealthMetrics, holdings: list[AnalyzedHolding]) -> list[PortfolioHealthAlert]:
    alerts: list[PortfolioHealthAlert] = []
    usa = metrics.geographic_exposure.get("usa", 0.0)
    if usa > 60:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="geographic_concentration",
                message=f"Il portafoglio è fortemente esposto al mercato statunitense ({usa:.1f}%).",
            )
        )
    if metrics.max_position_weight > 60:
        alerts.append(
            PortfolioHealthAlert(
                severity="critical",
                type="position_concentration",
                message=f"Una singola posizione domina il portafoglio ({metrics.max_position_weight:.1f}%).",
                details=build_position_concentration_details(holdings),
            )
        )
    elif metrics.max_position_weight > 40:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="position_concentration",
                message=f"Una posizione ha un peso elevato nel portafoglio ({metrics.max_position_weight:.1f}%).",
                details=build_position_concentration_details(holdings),
            )
        )
    if metrics.overlap_score > 70:
        alerts.append(
            PortfolioHealthAlert(
                severity="critical",
                type="etf_overlap",
                message=f"Diverse posizioni risultano molto ridondanti: la sovrapposizione tra ETF è molto alta ({metrics.overlap_score:.1f}%).",
                details=build_etf_overlap_details(holdings, metrics.overlap_score),
            )
        )
    elif metrics.overlap_score > 50:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="etf_overlap",
                message=f"Diverse posizioni risultano ridondanti: la sovrapposizione tra ETF è alta ({metrics.overlap_score:.1f}%).",
                details=build_etf_overlap_details(holdings, metrics.overlap_score),
            )
        )
    if metrics.portfolio_volatility is not None and metrics.portfolio_volatility > 15:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="portfolio_risk",
                message=f"La volatilità stimata del portafoglio è elevata ({metrics.portfolio_volatility:.1f}%).",
            )
        )
    if metrics.weighted_ter is not None and metrics.weighted_ter > 0.5:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="high_costs",
                message=f"Il costo medio ponderato dei fondi è relativamente alto ({metrics.weighted_ter:.2f}%).",
            )
        )
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda alert: (severity_order[alert.severity], alert.type))
    return alerts


def build_position_concentration_details(holdings: list[AnalyzedHolding]) -> dict[str, object] | None:
    ranked = sorted(holdings, key=lambda holding: holding.weight_pct, reverse=True)
    if not ranked:
        return None

    def serialize_holding(holding: AnalyzedHolding) -> dict[str, object]:
        return {
            "symbol": holding.symbol,
            "name": holding.name,
            "asset_type": holding.asset_type,
            "weight_pct": round(holding.weight_pct, 1),
            "market_value": round(holding.market_value, 2),
        }

    dominant = serialize_holding(ranked[0])
    top_positions = [serialize_holding(holding) for holding in ranked[:3]]
    return {
        "dominant_position": dominant,
        "top_positions": top_positions,
    }


def build_etf_overlap_details(holdings: list[AnalyzedHolding], overlap_score: float) -> dict[str, object] | None:
    fund_like_holdings = [holding for holding in holdings if holding.asset_type in {"etf", "fund"}]
    if len(fund_like_holdings) < 2:
        return None

    pairs: list[dict[str, object]] = []
    for index, left in enumerate(fund_like_holdings):
        for right in fund_like_holdings[index + 1 :]:
            estimated_overlap = estimate_overlap_between_assets(left, right)
            if estimated_overlap < 40:
                continue
            pair_weight = (left.weight_pct / 100.0) * (right.weight_pct / 100.0)
            pairs.append(
                {
                    "left": {
                        "symbol": left.symbol,
                        "name": left.name,
                        "weight_pct": round(left.weight_pct, 1),
                    },
                    "right": {
                        "symbol": right.symbol,
                        "name": right.name,
                        "weight_pct": round(right.weight_pct, 1),
                    },
                    "estimated_overlap_pct": round(estimated_overlap, 1),
                    "combined_weight_pct": round(left.weight_pct + right.weight_pct, 1),
                    "priority_score": estimated_overlap * pair_weight,
                }
            )

    if not pairs:
        return None

    top_pairs = sorted(
        pairs,
        key=lambda pair: (float(pair["estimated_overlap_pct"]), float(pair["priority_score"])),
        reverse=True,
    )[:3]
    for pair in top_pairs:
        pair.pop("priority_score", None)

    return {
        "overlap_score": round(overlap_score, 1),
        "pairs": top_pairs,
    }


def build_suggestions(metrics: PortfolioHealthMetrics, *, equity_weight: float) -> list[PortfolioHealthSuggestion]:
    suggestions: list[PortfolioHealthSuggestion] = []
    usa = metrics.geographic_exposure.get("usa", 0.0)
    emerging = metrics.geographic_exposure.get("emerging", 0.0)

    if usa > 60:
        suggestions.append(
            PortfolioHealthSuggestion(
                priority="medium",
                message="Valuta di aumentare l'esposizione ad azioni non statunitensi per migliorare la diversificazione.",
            )
        )
    if emerging < 5 and equity_weight >= 60:
        suggestions.append(
            PortfolioHealthSuggestion(
                priority="medium",
                message="Valuta di aggiungere una piccola allocazione ai mercati emergenti per ampliare l'esposizione azionaria.",
            )
        )
    if metrics.overlap_score > 50:
        suggestions.append(
            PortfolioHealthSuggestion(
                priority="high",
                message="Rivedi gli ETF azionari ampi con mandati simili e consolida le posizioni sovrapposte dove possibile.",
            )
        )
    if metrics.max_position_weight > 40:
        suggestions.append(
            PortfolioHealthSuggestion(
                priority="high" if metrics.max_position_weight > 60 else "medium",
                message="Ridurre la posizione più grande potrebbe migliorare il rischio di concentrazione e la stabilità del punteggio.",
            )
        )
    if metrics.weighted_ter is not None and metrics.weighted_ter > 0.3:
        suggestions.append(
            PortfolioHealthSuggestion(
                priority="low",
                message="Confronta i costi dei fondi con ETF simili a commissioni più basse per migliorare l'efficienza dei costi.",
            )
        )
    return suggestions


def compute_total_score(category_scores: PortfolioHealthCategoryScores) -> int:
    return (
        category_scores.diversification
        + category_scores.risk
        + category_scores.concentration
        + category_scores.overlap
        + category_scores.cost_efficiency
    )


def build_summary(
    metrics: PortfolioHealthMetrics,
    category_scores: PortfolioHealthCategoryScores,
) -> PortfolioHealthSummary:
    if metrics.portfolio_volatility is None:
        risk_level = "unknown"
    elif metrics.portfolio_volatility < 10:
        risk_level = "low"
    elif metrics.portfolio_volatility <= 15:
        risk_level = "medium"
    else:
        risk_level = "high"

    if category_scores.diversification >= 22:
        diversification = "excellent"
    elif category_scores.diversification >= 17:
        diversification = "good"
    elif category_scores.diversification >= 11:
        diversification = "moderate"
    else:
        diversification = "weak"

    if metrics.overlap_score == 0:
        overlap = "low"
    elif metrics.overlap_score <= 40:
        overlap = "low"
    elif metrics.overlap_score <= 60:
        overlap = "moderate"
    else:
        overlap = "high"

    if metrics.weighted_ter is None:
        cost_efficiency = "unknown"
    elif metrics.weighted_ter <= 0.3:
        cost_efficiency = "low_cost"
    elif metrics.weighted_ter <= 0.5:
        cost_efficiency = "moderate_cost"
    else:
        cost_efficiency = "high_cost"

    return PortfolioHealthSummary(
        risk_level=risk_level,
        diversification=diversification,
        overlap=overlap,
        cost_efficiency=cost_efficiency,
    )


def _is_equity_like(holding: AnalyzedHolding) -> bool:
    return holding.asset_type.lower() in {"stock", "etf", "fund"}


NUM_SIMULATIONS = 1_000
MAX_PROJECTION_YEARS = 20
PROJECTION_HORIZONS = [5, 10, 20]


def run_monte_carlo_projection(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str | None = None,
) -> MonteCarloProjectionResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    holdings = _load_holdings(repo, portfolio_id, user_id)
    if not holdings:
        return _empty_monte_carlo_response(portfolio_id)

    mu_annual, sigma_annual = _compute_portfolio_return_params(repo, holdings)
    if sigma_annual == 0.0:
        return _empty_monte_carlo_response(portfolio_id)

    projections = _simulate_paths(mu_annual, sigma_annual)

    return MonteCarloProjectionResponse(
        portfolio_id=portfolio_id,
        num_simulations=NUM_SIMULATIONS,
        horizons=PROJECTION_HORIZONS,
        projections=projections,
        annualized_mean_return_pct=round(mu_annual * 100, 2),
        annualized_volatility_pct=round(sigma_annual * 100, 2),
    )


def run_decumulation_plan(
    repo: PortfolioRepository,
    portfolio_id: int,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float = 0.0,
    current_age: int | None = None,
    user_id: str | None = None,
) -> DecumulationPlanResponse:
    if not user_id:
        raise ValueError("Utente non valido")

    summary = repo.get_summary(portfolio_id, user_id)
    initial_capital = max(0.0, float(summary.market_value) + float(summary.cash_balance))
    holdings = _load_holdings(repo, portfolio_id, user_id)

    mu_annual, sigma_annual = _compute_portfolio_return_params(repo, holdings) if holdings else (0.0, 0.0)
    sustainable_withdrawal = _solve_sustainable_withdrawal(
        initial_capital=initial_capital,
        years=years,
        annual_return_pct=mu_annual * 100,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
    )

    if initial_capital <= 0:
        return _empty_decumulation_response(
            portfolio_id=portfolio_id,
            annual_withdrawal=annual_withdrawal,
            years=years,
            inflation_rate_pct=inflation_rate_pct,
            other_income_annual=other_income_annual,
            current_age=current_age,
        )

    paths = _simulate_decumulation_paths(
        initial_capital=initial_capital,
        annual_withdrawal=annual_withdrawal,
        years=years,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        mu_annual=mu_annual,
        sigma_annual=sigma_annual,
    )
    final_values = sorted(path["ending_capitals"][-1] for path in paths)
    success_count = sum(1 for path in paths if path["ending_capitals"][-1] > 0)
    projections = _build_decumulation_projections(
        paths=paths,
        years=years,
        annual_withdrawal=annual_withdrawal,
        inflation_rate_pct=inflation_rate_pct,
        other_income_annual=other_income_annual,
        current_age=current_age,
    )
    depletion_year_p50 = next((projection.year for projection in projections if projection.p50_ending_capital <= 0), None)

    return DecumulationPlanResponse(
        portfolio_id=portfolio_id,
        initial_capital=round(initial_capital, 2),
        annual_withdrawal=round(max(0.0, annual_withdrawal), 2),
        annual_other_income=round(max(0.0, other_income_annual), 2),
        inflation_rate_pct=round(max(0.0, inflation_rate_pct), 2),
        horizon_years=years,
        num_simulations=NUM_SIMULATIONS,
        annualized_mean_return_pct=round(mu_annual * 100, 2),
        annualized_volatility_pct=round(sigma_annual * 100, 2),
        sustainable_withdrawal=round(max(0.0, sustainable_withdrawal), 2),
        success_rate_pct=round((success_count / NUM_SIMULATIONS) * 100, 1),
        depletion_probability_pct=round(((NUM_SIMULATIONS - success_count) / NUM_SIMULATIONS) * 100, 1),
        p25_terminal_value=round(_percentile(final_values, 25), 2),
        p50_terminal_value=round(_percentile(final_values, 50), 2),
        p75_terminal_value=round(_percentile(final_values, 75), 2),
        depletion_year_p50=depletion_year_p50,
        projections=projections,
    )


def _compute_portfolio_return_params(
    repo: PortfolioRepository,
    holdings: list[AnalyzedHolding],
) -> tuple[float, float]:
    asset_ids = [h.asset_id for h in holdings if h.asset_type != "cash"]
    if not asset_ids:
        return 0.0, 0.0

    start_date = date.today() - timedelta(days=370)
    with repo.engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                select asset_id, price_date, close::float8 as close
                from price_bars_1d
                where asset_id = any(:asset_ids)
                  and price_date >= :start_date
                order by asset_id asc, price_date asc
                """
            ),
            {"asset_ids": asset_ids, "start_date": start_date},
        ).mappings().all()

    prices_by_asset: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        close = float(row["close"])
        if close > 0 and math.isfinite(close):
            prices_by_asset[int(row["asset_id"])].append(close)

    weighted_mu = 0.0
    weighted_sigma = 0.0
    covered_weight = 0.0

    for holding in holdings:
        series = prices_by_asset.get(holding.asset_id, [])
        if len(series) < 20:
            continue
        log_returns = [
            math.log(curr / prev)
            for prev, curr in zip(series, series[1:])
            if prev > 0 and curr > 0
        ]
        if len(log_returns) < 20:
            continue

        mu_daily = statistics.mean(log_returns)
        sigma_daily = statistics.pstdev(log_returns)
        mu_ann = mu_daily * 252
        sigma_ann = sigma_daily * math.sqrt(252)
        weight_fraction = holding.weight_pct / 100.0

        weighted_mu += mu_ann * weight_fraction
        weighted_sigma += sigma_ann * weight_fraction
        covered_weight += weight_fraction

    if covered_weight == 0:
        return 0.0, 0.0

    return weighted_mu / covered_weight, weighted_sigma / covered_weight


def _simulate_paths(
    mu_annual: float,
    sigma_annual: float,
) -> list[MonteCarloYearProjection]:
    drift = mu_annual - 0.5 * sigma_annual**2
    rng = random.Random(42)

    # Each simulation: cumulative log-return at each year
    all_paths: list[list[float]] = []
    for _ in range(NUM_SIMULATIONS):
        cum = 0.0
        path = [100.0]
        for _ in range(MAX_PROJECTION_YEARS):
            shock = rng.gauss(0, 1)
            cum += drift + sigma_annual * shock
            path.append(100.0 * math.exp(cum))
        all_paths.append(path)

    projections: list[MonteCarloYearProjection] = []
    for year_idx in range(MAX_PROJECTION_YEARS + 1):
        values = sorted(p[year_idx] for p in all_paths)
        projections.append(
            MonteCarloYearProjection(
                year=year_idx,
                p10=round(_percentile(values, 10), 1),
                p25=round(_percentile(values, 25), 1),
                p50=round(_percentile(values, 50), 1),
                p75=round(_percentile(values, 75), 1),
                p90=round(_percentile(values, 90), 1),
            )
        )
    return projections


def _simulate_decumulation_paths(
    *,
    initial_capital: float,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    mu_annual: float,
    sigma_annual: float,
) -> list[dict[str, list[float]]]:
    drift = mu_annual - 0.5 * sigma_annual**2
    inflation = max(0.0, inflation_rate_pct) / 100.0
    rng = random.Random(42)
    paths: list[dict[str, list[float]]] = []

    for _ in range(NUM_SIMULATIONS):
        capital = initial_capital
        withdrawal = max(0.0, annual_withdrawal)
        ending_capitals: list[float] = []
        effective_rates: list[float] = []
        depleted_flags: list[float] = []

        for _year in range(years):
            starting_capital = capital
            annual_return = math.exp(drift + sigma_annual * rng.gauss(0, 1)) - 1 if sigma_annual > 0 else mu_annual
            capital = max(0.0, capital * (1 + annual_return))
            net_withdrawal = max(0.0, withdrawal - max(0.0, other_income_annual))
            effective_rates.append((net_withdrawal / starting_capital) * 100 if starting_capital > 0 else 0.0)
            capital = max(0.0, capital - net_withdrawal)
            ending_capitals.append(capital)
            depleted_flags.append(1.0 if capital <= 0 else 0.0)
            withdrawal *= (1 + inflation)

        paths.append(
            {
                "ending_capitals": ending_capitals,
                "effective_rates": effective_rates,
                "depleted_flags": depleted_flags,
            }
        )

    return paths


def _build_decumulation_projections(
    *,
    paths: list[dict[str, list[float]]],
    years: int,
    annual_withdrawal: float,
    inflation_rate_pct: float,
    other_income_annual: float,
    current_age: int | None,
) -> list[DecumulationYearProjection]:
    inflation = max(0.0, inflation_rate_pct) / 100.0
    gross_withdrawal = max(0.0, annual_withdrawal)
    projections: list[DecumulationYearProjection] = []

    for year_index in range(years):
        capitals = sorted(path["ending_capitals"][year_index] for path in paths)
        rates = sorted(path["effective_rates"][year_index] for path in paths)
        depleted_count = sum(path["depleted_flags"][year_index] for path in paths)
        net_withdrawal = max(0.0, gross_withdrawal - max(0.0, other_income_annual))

        projections.append(
            DecumulationYearProjection(
                year=year_index + 1,
                age=(current_age + year_index + 1) if current_age else None,
                gross_withdrawal=round(gross_withdrawal, 2),
                net_withdrawal=round(net_withdrawal, 2),
                p25_ending_capital=round(_percentile(capitals, 25), 2),
                p50_ending_capital=round(_percentile(capitals, 50), 2),
                p75_ending_capital=round(_percentile(capitals, 75), 2),
                p50_effective_withdrawal_rate_pct=round(_percentile(rates, 50), 2),
                depletion_probability_pct=round((depleted_count / NUM_SIMULATIONS) * 100, 1),
            )
        )
        gross_withdrawal *= (1 + inflation)

    return projections


def _solve_sustainable_withdrawal(
    *,
    initial_capital: float,
    years: int,
    annual_return_pct: float,
    inflation_rate_pct: float,
    other_income_annual: float,
) -> float:
    if initial_capital <= 0 or years <= 0:
        return 0.0

    nominal = annual_return_pct / 100.0
    inflation = inflation_rate_pct / 100.0
    real_rate = ((1 + nominal) / (1 + inflation)) - 1

    if abs(real_rate) < 1e-9:
        return max(0.0, initial_capital / years + other_income_annual)

    denominator = 1 - (1 + real_rate) ** (-years)
    if denominator <= 0:
        return max(0.0, other_income_annual)
    return max(0.0, initial_capital * real_rate / denominator + other_income_annual)


def _percentile(sorted_values: list[float], pct: int) -> float:
    n = len(sorted_values)
    k = (pct / 100) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def _empty_monte_carlo_response(portfolio_id: int) -> MonteCarloProjectionResponse:
    return MonteCarloProjectionResponse(
        portfolio_id=portfolio_id,
        num_simulations=0,
        horizons=PROJECTION_HORIZONS,
        projections=[],
        annualized_mean_return_pct=0.0,
        annualized_volatility_pct=0.0,
    )


def _empty_decumulation_response(
    *,
    portfolio_id: int,
    annual_withdrawal: float,
    years: int,
    inflation_rate_pct: float,
    other_income_annual: float,
    current_age: int | None,
) -> DecumulationPlanResponse:
    projections = [
        DecumulationYearProjection(
            year=year,
            age=(current_age + year) if current_age else None,
            gross_withdrawal=round(max(0.0, annual_withdrawal) * ((1 + max(0.0, inflation_rate_pct) / 100.0) ** (year - 1)), 2),
            net_withdrawal=round(max(0.0, max(0.0, annual_withdrawal) - max(0.0, other_income_annual)), 2),
            p25_ending_capital=0.0,
            p50_ending_capital=0.0,
            p75_ending_capital=0.0,
            p50_effective_withdrawal_rate_pct=0.0,
            depletion_probability_pct=100.0,
        )
        for year in range(1, years + 1)
    ]
    return DecumulationPlanResponse(
        portfolio_id=portfolio_id,
        initial_capital=0.0,
        annual_withdrawal=round(max(0.0, annual_withdrawal), 2),
        annual_other_income=round(max(0.0, other_income_annual), 2),
        inflation_rate_pct=round(max(0.0, inflation_rate_pct), 2),
        horizon_years=years,
        num_simulations=0,
        annualized_mean_return_pct=0.0,
        annualized_volatility_pct=0.0,
        sustainable_withdrawal=0.0,
        success_rate_pct=0.0,
        depletion_probability_pct=100.0,
        p25_terminal_value=0.0,
        p50_terminal_value=0.0,
        p75_terminal_value=0.0,
        depletion_year_p50=1 if years > 0 else None,
        projections=projections,
    )
