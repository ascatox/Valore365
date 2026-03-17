import logging
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import text

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    PortfolioHealthAlert,
    PortfolioHealthCategoryScores,
    PortfolioHealthMetrics,
    PortfolioHealthResponse,
    PortfolioHealthSuggestion,
    PortfolioHealthSummary,
)
from ...constants.geo_classification import (
    REGIONS,
    GLOBAL_EQUITY_SPLIT,
    GLOBAL_BOND_SPLIT,
    EUROPE_SUFFIXES,
    EMERGING_CURRENCIES,
    EUROPE_CURRENCIES,
)
from ._holdings import AnalyzedHolding, _load_holdings, _is_equity_like

logger = logging.getLogger(__name__)


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

    geographic_exposure = compute_geographic_exposure(holdings, repo=repo)
    sector_exposure = compute_sector_exposure(holdings, repo=repo)
    max_position_weight = compute_max_position_weight(holdings)
    overlap_score = compute_overlap_score(holdings)
    portfolio_volatility = compute_portfolio_volatility(repo, holdings)
    weighted_ter = compute_weighted_ter(holdings, repo=repo)
    top3_weight = round(sum(h.weight_pct for h in holdings[:3]), 2)
    equity_weight = round(sum(h.weight_pct for h in holdings if _is_equity_like(h)), 2)

    metrics = PortfolioHealthMetrics(
        geographic_exposure=geographic_exposure,
        sector_exposure=sector_exposure,
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


def _country_to_region(country_name: str) -> str:
    """Map a country name to one of our standard regions."""
    name = country_name.strip().lower()
    usa_names = {"united states", "usa", "us", "stati uniti", "united states of america"}
    europe_names = {
        "germany", "france", "united kingdom", "uk", "netherlands", "switzerland",
        "spain", "italy", "sweden", "denmark", "finland", "norway", "belgium",
        "ireland", "austria", "portugal", "luxembourg", "greece", "poland",
        "czech republic", "hungary", "romania", "croatia",
        "germania", "francia", "regno unito", "paesi bassi", "svizzera",
        "spagna", "italia", "svezia", "danimarca", "finlandia", "norvegia",
        "belgio", "irlanda", "austria", "portogallo", "lussemburgo", "grecia",
    }
    emerging_names = {
        "china", "india", "brazil", "taiwan", "south korea", "mexico",
        "south africa", "indonesia", "thailand", "malaysia", "philippines",
        "chile", "colombia", "peru", "turkey", "saudi arabia", "qatar",
        "united arab emirates", "egypt", "pakistan", "vietnam", "nigeria",
        "cina", "brasile", "corea del sud", "messico", "sudafrica",
    }
    if name in usa_names:
        return "usa"
    if name in europe_names:
        return "europe"
    if name in emerging_names:
        return "emerging"
    return "other"


def compute_geographic_exposure(
    holdings: list[AnalyzedHolding],
    repo: PortfolioRepository | None = None,
) -> dict[str, float]:
    # Load enrichment data for all holdings if available
    enrichment_map: dict[int, dict] = {}
    if repo:
        try:
            asset_ids = [h.asset_id for h in holdings]
            enrichment_map = repo.get_etf_enrichment_bulk(asset_ids)
        except Exception:
            pass

    exposure = {region: 0.0 for region in REGIONS}
    for holding in holdings:
        enrich = enrichment_map.get(holding.asset_id)
        if enrich and enrich.get("country_weights"):
            # Use real country data from justETF
            for cw in enrich["country_weights"]:
                region = _country_to_region(cw["name"])
                exposure[region] += holding.weight_pct * (cw["percentage"] / 100.0)
        else:
            # Fallback to heuristic
            profile = infer_region_profile(holding)
            for region, split in profile.items():
                exposure[region] += holding.weight_pct * (split / 100.0)

    normalized = {region: round(max(0.0, value), 1) for region, value in exposure.items() if value > 0}
    total = round(sum(normalized.values()), 1)
    if total and total != 100.0:
        diff = round(100.0 - total, 1)
        normalized["other"] = round(normalized.get("other", 0.0) + diff, 1)
    return normalized


def compute_sector_exposure(
    holdings: list[AnalyzedHolding],
    repo: PortfolioRepository | None = None,
) -> dict[str, float]:
    """Compute portfolio-level sector exposure using justETF enrichment data."""
    enrichment_map: dict[int, dict] = {}
    if repo:
        try:
            asset_ids = [h.asset_id for h in holdings]
            enrichment_map = repo.get_etf_enrichment_bulk(asset_ids)
        except Exception:
            pass

    sector_totals: dict[str, float] = {}
    for holding in holdings:
        enrich = enrichment_map.get(holding.asset_id)
        if enrich and enrich.get("sector_weights"):
            for sw in enrich["sector_weights"]:
                name = sw["name"]
                sector_totals[name] = sector_totals.get(name, 0.0) + holding.weight_pct * (sw["percentage"] / 100.0)

    if not sector_totals:
        return {}

    # Normalize and sort by weight descending
    result = {k: round(v, 1) for k, v in sorted(sector_totals.items(), key=lambda x: -x[1]) if v >= 0.1}
    return result


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


def compute_weighted_ter(
    holdings: list[AnalyzedHolding],
    repo: PortfolioRepository | None = None,
) -> float | None:
    # Try to fetch TER from justETF enrichment first, then yFinance metadata
    db_ter: dict[int, float] = {}
    if repo:
        try:
            asset_ids = [h.asset_id for h in holdings]
            # justETF enrichment (preferred — more accurate)
            enrich_map = repo.get_etf_enrichment_bulk(asset_ids)
            for aid, enrich in enrich_map.items():
                if enrich.get("ter") is not None:
                    db_ter[aid] = enrich["ter"]  # justETF already returns percentage (e.g. 0.22)
        except Exception:
            pass
        try:
            # yFinance metadata as fallback
            asset_ids = [h.asset_id for h in holdings]
            meta_map = repo.get_asset_metadata_bulk(asset_ids)
            for aid, meta in meta_map.items():
                if aid not in db_ter and meta.expense_ratio is not None:
                    db_ter[aid] = meta.expense_ratio * 100
        except Exception:
            pass

    weighted_cost = 0.0
    covered_weight = 0.0
    for holding in holdings:
        ter = db_ter.get(holding.asset_id) or infer_ter(holding)
        if ter is None:
            continue
        weight_fraction = holding.weight_pct / 100.0
        weighted_cost += ter * weight_fraction
        covered_weight += weight_fraction
    if covered_weight == 0:
        return None
    return round(weighted_cost / covered_weight, 2)


def infer_ter(holding: AnalyzedHolding) -> float | None:
    """Fallback TER inference via pattern matching when DB metadata is missing."""
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
                message=f"Il portafoglio \u00e8 fortemente esposto al mercato statunitense ({usa:.1f}%).",
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
                message=f"Diverse posizioni risultano molto ridondanti: la sovrapposizione tra ETF \u00e8 molto alta ({metrics.overlap_score:.1f}%).",
                details=build_etf_overlap_details(holdings, metrics.overlap_score),
            )
        )
    elif metrics.overlap_score > 50:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="etf_overlap",
                message=f"Diverse posizioni risultano ridondanti: la sovrapposizione tra ETF \u00e8 alta ({metrics.overlap_score:.1f}%).",
                details=build_etf_overlap_details(holdings, metrics.overlap_score),
            )
        )
    if metrics.portfolio_volatility is not None and metrics.portfolio_volatility > 15:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="portfolio_risk",
                message=f"La volatilit\u00e0 stimata del portafoglio \u00e8 elevata ({metrics.portfolio_volatility:.1f}%).",
            )
        )
    if metrics.weighted_ter is not None and metrics.weighted_ter > 0.5:
        alerts.append(
            PortfolioHealthAlert(
                severity="warning",
                type="high_costs",
                message=f"Il costo medio ponderato dei fondi \u00e8 relativamente alto ({metrics.weighted_ter:.2f}%).",
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
                message="Ridurre la posizione pi\u00f9 grande potrebbe migliorare il rischio di concentrazione e la stabilit\u00e0 del punteggio.",
            )
        )
    if metrics.weighted_ter is not None and metrics.weighted_ter > 0.3:
        suggestions.append(
            PortfolioHealthSuggestion(
                priority="low",
                message="Confronta i costi dei fondi con ETF simili a commissioni pi\u00f9 basse per migliorare l'efficienza dei costi.",
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
