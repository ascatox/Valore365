import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from ..config import get_settings
from ..copilot.config import CopilotConfig, resolve_copilot_config
from ..repository import PortfolioRepository
from ..schemas.instant_portfolio_analyzer import (
    InstantAnalyzeCta,
    InstantAnalyzeLineError,
    InstantAnalyzeRequest,
    InstantAnalyzeResponse,
    InstantAnalyzeUnresolvedItem,
    InstantInsightExplainResponse,
    ParsedPositionInput,
    PortfolioAnalyzeAlert,
    PortfolioAnalyzeMetrics,
    PortfolioAnalyzeSuggestion,
    PortfolioAnalyzeSummary,
    PortfolioTopInsight,
    ResolvedPosition,
)
from .portfolio_doctor import (
    AnalyzedHolding,
    build_alerts,
    build_suggestions,
    build_summary,
    compute_category_scores,
    compute_geographic_exposure,
    compute_max_position_weight,
    compute_overlap_score,
    compute_total_score,
)

IDENTIFIER_PATTERN = re.compile(r"^[A-Z0-9._-]{1,32}$")

RISK_SCORES = {
    "Equity": 5.0,
    "Bond": 2.0,
    "Gold": 3.0,
    "Cash": 1.0,
}

DRAWDOWN_SCORES = {
    "Equity": 0.35,
    "Bond": 0.10,
    "Gold": 0.15,
    "Cash": 0.0,
}

REGION_LABELS = {
    "usa": "USA",
    "europe": "Europe",
    "emerging": "Emerging Markets",
    "other": "Other",
}

EXPLAIN_SYSTEM_PROMPT = (
    "Sei un educatore finanziario.\n\n"
    "Non dare consigli operativi.\n"
    "Spiega in modo semplice.\n"
    "Massimo 5 frasi.\n"
    "Usa esempi concreti."
)


@dataclass
class CatalogAsset:
    symbol: str
    isin: str | None
    name: str
    asset_type: str
    quote_currency: str
    estimated_volatility: float | None
    ter: float | None
    overlap_tags: list[str]
    region_profile: dict[str, float]
    top_holdings: dict[str, float]
    asset_id: int | None = None


@dataclass
class ResolvedCatalogPosition:
    identifier: str
    value: float
    line: int | None
    raw: str | None
    asset: CatalogAsset


@dataclass
class NormalizedInsightAsset:
    ticker: str
    name: str
    weight: float
    asset_class: str
    geo_exposure: dict[str, float]
    top_holdings: dict[str, float]
    geo_confidence: int
    holdings_confidence: int


class InstantPortfolioAnalysisError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        parse_errors: list[InstantAnalyzeLineError] | None = None,
        unresolved: list[InstantAnalyzeUnresolvedItem] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = {
            "parse_errors": [item.model_dump() for item in (parse_errors or [])],
            "unresolved": [item.model_dump() for item in (unresolved or [])],
        }


def analyze_public_portfolio(repo: PortfolioRepository, payload: InstantAnalyzeRequest) -> InstantAnalyzeResponse:
    normalized_positions, parse_errors = parse_request_positions(payload)
    resolved_positions, unresolved = resolve_positions(repo, normalized_positions)

    if not resolved_positions:
        raise InstantPortfolioAnalysisError(
            "No valid positions found",
            parse_errors=parse_errors,
            unresolved=unresolved,
        )

    total_value = round(sum(position.value for position in resolved_positions), 2)
    holdings = build_analyzed_holdings(resolved_positions, total_value)
    metrics = compute_public_metrics(resolved_positions, holdings, repo=repo)
    normalized_assets = build_normalized_assets(repo, resolved_positions)
    insights = generate_top_insights(normalized_assets, metrics)
    equity_weight = round(
        sum(holding.weight_pct for holding in holdings if holding.asset_type in {"stock", "etf", "fund"}),
        2,
    )
    category_scores = compute_category_scores(
        metrics,
        top3_weight=round(sum(holding.weight_pct for holding in holdings[:3]), 2),
        equity_weight=equity_weight,
    )
    score = compute_total_score(category_scores)
    summary = build_summary(metrics, category_scores)
    alerts = transform_alerts(build_alerts(metrics, holdings))
    suggestions = transform_suggestions(build_suggestions(metrics, equity_weight=equity_weight))

    return InstantAnalyzeResponse(
        summary=PortfolioAnalyzeSummary(
            total_value=total_value,
            score=score,
            risk_level=summary.risk_level,
            diversification=summary.diversification,
            overlap=summary.overlap,
            cost_efficiency=summary.cost_efficiency,
        ),
        positions=[
            ResolvedPosition(
                identifier=position.identifier,
                resolved_symbol=position.asset.symbol,
                resolved_name=position.asset.name,
                value=round(position.value, 2),
                weight=round(position.value / total_value * 100.0, 2),
            )
            for position in resolved_positions
        ],
        unresolved=unresolved,
        parse_errors=parse_errors,
        metrics=PortfolioAnalyzeMetrics(
            geographic_exposure=metrics.geographic_exposure,
            asset_allocation=metrics.asset_allocation,
            max_position_weight=metrics.max_position_weight,
            overlap_score=metrics.overlap_score,
            portfolio_volatility=metrics.portfolio_volatility,
            weighted_ter=metrics.weighted_ter,
            risk_score=metrics.risk_score,
            estimated_drawdown=metrics.estimated_drawdown,
        ),
        category_scores=category_scores,
        alerts=alerts,
        suggestions=suggestions,
        insights=insights,
        cta=InstantAnalyzeCta(
            show_signup=True,
            message="Crea un account gratuito per salvare e monitorare questo portafoglio nel tempo.",
        ),
    )


def explain_public_insight(insight: PortfolioTopInsight) -> InstantInsightExplainResponse:
    template = build_insight_explanation_template(insight)
    settings = get_settings()
    config = resolve_copilot_config(settings)

    if config is None:
        return InstantInsightExplainResponse(
            insight_id=insight.id,
            explanation=template,
            source="template",
        )

    try:
        explanation = generate_ai_explanation(config, insight)
        return InstantInsightExplainResponse(
            insight_id=insight.id,
            explanation=explanation,
            source="ai",
        )
    except Exception:
        return InstantInsightExplainResponse(
            insight_id=insight.id,
            explanation=template,
            source="template",
        )


def parse_request_positions(payload: InstantAnalyzeRequest) -> tuple[list[tuple[ParsedPositionInput, int | None, str | None]], list[InstantAnalyzeLineError]]:
    if payload.input_mode == "raw_text":
        if not payload.raw_text or not payload.raw_text.strip():
            raise ValueError("Raw text input is required")
        return parse_raw_text(payload.raw_text)

    if not payload.positions:
        raise ValueError("At least one position is required")

    normalized: list[tuple[ParsedPositionInput, int | None, str | None]] = []
    for item in payload.positions:
        identifier = item.identifier.strip().upper()
        if not identifier:
            continue
        normalized.append((ParsedPositionInput(identifier=identifier, value=item.value), None, None))
    if not normalized:
        raise ValueError("No valid positions found")
    return normalized, []


def parse_raw_text(raw_text: str) -> tuple[list[tuple[ParsedPositionInput, int | None, str | None]], list[InstantAnalyzeLineError]]:
    results: list[tuple[ParsedPositionInput, int | None, str | None]] = []
    errors: list[InstantAnalyzeLineError] = []
    max_line_length = get_settings().public_instant_analyzer_max_line_length

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if len(raw_line) > max_line_length:
            errors.append(
                InstantAnalyzeLineError(
                    line=line_number,
                    raw=raw_line,
                    error=f"Line is too long (max {max_line_length} characters)",
                )
            )
            continue
        parts = line.split()
        if len(parts) < 2:
            errors.append(InstantAnalyzeLineError(line=line_number, raw=raw_line, error="Expected format: IDENTIFIER VALUE"))
            continue

        identifier = parts[0].strip().upper()
        if not IDENTIFIER_PATTERN.fullmatch(identifier):
            errors.append(InstantAnalyzeLineError(line=line_number, raw=raw_line, error="Invalid identifier format"))
            continue
        value_token = parts[-1].replace(".", "").replace(",", ".")
        try:
            value = float(value_token)
            if value <= 0:
                raise ValueError("non-positive")
        except ValueError:
            errors.append(InstantAnalyzeLineError(line=line_number, raw=raw_line, error="Invalid numeric value"))
            continue

        results.append((ParsedPositionInput(identifier=identifier, value=value), line_number, raw_line))

    if not results and errors:
        return [], errors
    return results, errors


def resolve_positions(
    repo: PortfolioRepository,
    positions: list[tuple[ParsedPositionInput, int | None, str | None]],
) -> tuple[list[ResolvedCatalogPosition], list[InstantAnalyzeUnresolvedItem]]:
    catalog = load_asset_catalog()
    resolved: list[ResolvedCatalogPosition] = []
    unresolved: list[InstantAnalyzeUnresolvedItem] = []

    for item, line, raw in positions:
        asset = resolve_identifier(repo, item.identifier, catalog)
        if asset is None:
            unresolved.append(
                InstantAnalyzeUnresolvedItem(
                    identifier=item.identifier,
                    raw=raw,
                    line=line,
                    error="Asset not found in the supported catalog",
                )
            )
            continue
        resolved.append(
            ResolvedCatalogPosition(
                identifier=item.identifier,
                value=item.value,
                line=line,
                raw=raw,
                asset=asset,
            )
        )
    return resolved, unresolved


def build_analyzed_holdings(resolved_positions: list[ResolvedCatalogPosition], total_value: float) -> list[AnalyzedHolding]:
    holdings = [
        AnalyzedHolding(
            asset_id=position.asset.asset_id or 0,
            symbol=position.asset.symbol,
            name=position.asset.name,
            asset_type=position.asset.asset_type,
            quote_currency=position.asset.quote_currency,
            market_value=position.value,
            weight_pct=round(position.value / total_value * 100.0, 2),
        )
        for position in resolved_positions
    ]
    holdings.sort(key=lambda holding: holding.market_value, reverse=True)
    return holdings


def compute_public_metrics(
    resolved_positions: list[ResolvedCatalogPosition],
    holdings: list[AnalyzedHolding],
    *,
    repo: PortfolioRepository,
) -> PortfolioAnalyzeMetrics:
    geographic_exposure = compute_geographic_exposure_with_catalog(resolved_positions, holdings)
    asset_allocation = compute_asset_allocation_from_catalog(resolved_positions)
    max_position_weight = compute_max_position_weight(holdings)
    overlap_score = compute_overlap_score(holdings)
    portfolio_volatility = compute_portfolio_volatility_from_catalog(resolved_positions)
    weighted_ter = compute_weighted_ter_from_catalog(resolved_positions)
    risk_score = compute_risk_score_from_catalog(resolved_positions)
    estimated_drawdown = compute_drawdown_from_catalog(resolved_positions)

    return PortfolioAnalyzeMetrics(
        geographic_exposure=geographic_exposure,
        asset_allocation=asset_allocation,
        max_position_weight=max_position_weight,
        overlap_score=overlap_score,
        portfolio_volatility=portfolio_volatility,
        weighted_ter=weighted_ter,
        risk_score=risk_score,
        estimated_drawdown=estimated_drawdown,
    )


def build_normalized_assets(
    repo: PortfolioRepository,
    resolved_positions: list[ResolvedCatalogPosition],
) -> list[NormalizedInsightAsset]:
    total_value = sum(position.value for position in resolved_positions)
    if total_value <= 0:
        return []

    enrichment_map: dict[int, dict] = {}
    asset_ids = [position.asset.asset_id for position in resolved_positions if position.asset.asset_id]
    if asset_ids and hasattr(repo, "get_etf_enrichment_bulk"):
        try:
            enrichment_map = repo.get_etf_enrichment_bulk(asset_ids)
        except Exception:
            enrichment_map = {}

    normalized_assets: list[NormalizedInsightAsset] = []
    for position in resolved_positions:
        enrich = enrichment_map.get(position.asset.asset_id or -1)
        geo_exposure, geo_confidence = build_geo_exposure(position.asset, enrich)
        top_holdings, holdings_confidence = build_top_holdings(position.asset, enrich)
        normalized_assets.append(
            NormalizedInsightAsset(
                ticker=position.asset.symbol,
                name=position.asset.name,
                weight=position.value / total_value,
                asset_class=map_asset_class(position.asset.asset_type, position.asset.name, position.asset.symbol),
                geo_exposure=geo_exposure,
                top_holdings=top_holdings,
                geo_confidence=geo_confidence,
                holdings_confidence=holdings_confidence,
            )
        )
    return normalized_assets


def compute_geographic_exposure_with_catalog(
    resolved_positions: list[ResolvedCatalogPosition],
    holdings: list[AnalyzedHolding],
) -> dict[str, float]:
    exposure = {"usa": 0.0, "europe": 0.0, "emerging": 0.0, "other": 0.0}
    by_symbol = {position.asset.symbol: position for position in resolved_positions}
    for holding in holdings:
        position = by_symbol.get(holding.symbol)
        if position is None:
            continue
        profile = position.asset.region_profile or {}
        if profile:
            for region, weight in profile.items():
                exposure[region] = exposure.get(region, 0.0) + holding.weight_pct * (weight / 100.0)
        else:
            fallback = compute_geographic_exposure([holding])
            for region, weight in fallback.items():
                exposure[region] = exposure.get(region, 0.0) + weight
    normalized = {key: round(value, 1) for key, value in exposure.items() if value > 0}
    total = round(sum(normalized.values()), 1)
    if total and total != 100.0:
        normalized["other"] = round(normalized.get("other", 0.0) + (100.0 - total), 1)
    return normalized


def compute_portfolio_volatility_from_catalog(resolved_positions: list[ResolvedCatalogPosition]) -> float | None:
    weighted = 0.0
    covered = 0.0
    total_value = sum(position.value for position in resolved_positions)
    if total_value <= 0:
        return None
    for position in resolved_positions:
        volatility = position.asset.estimated_volatility
        if volatility is None:
            volatility = fallback_volatility(position.asset.asset_type)
        if volatility is None:
            continue
        weight = position.value / total_value
        weighted += volatility * weight
        covered += weight
    if covered == 0:
        return None
    return round(weighted / covered, 1)


def compute_weighted_ter_from_catalog(resolved_positions: list[ResolvedCatalogPosition]) -> float | None:
    weighted = 0.0
    covered = 0.0
    total_value = sum(position.value for position in resolved_positions)
    if total_value <= 0:
        return None
    for position in resolved_positions:
        ter = position.asset.ter
        if ter is None:
            continue
        weight = position.value / total_value
        weighted += ter * weight
        covered += weight
    if covered == 0:
        return None
    return round(weighted / covered, 2)


def compute_asset_allocation_from_catalog(resolved_positions: list[ResolvedCatalogPosition]) -> dict[str, float]:
    total_value = sum(position.value for position in resolved_positions)
    if total_value <= 0:
        return {}

    allocation: dict[str, float] = defaultdict(float)
    for position in resolved_positions:
        asset_class = map_asset_class(position.asset.asset_type, position.asset.name, position.asset.symbol)
        allocation[asset_class] += position.value / total_value

    return {asset_class: round(weight * 100.0, 1) for asset_class, weight in allocation.items() if weight > 0}


def compute_risk_score_from_catalog(resolved_positions: list[ResolvedCatalogPosition]) -> float:
    total_value = sum(position.value for position in resolved_positions)
    if total_value <= 0:
        return 0.0

    score = 0.0
    for position in resolved_positions:
        asset_class = map_asset_class(position.asset.asset_type, position.asset.name, position.asset.symbol)
        score += (position.value / total_value) * RISK_SCORES.get(asset_class, 3.0)
    return round(score, 2)


def compute_drawdown_from_catalog(resolved_positions: list[ResolvedCatalogPosition]) -> float:
    total_value = sum(position.value for position in resolved_positions)
    if total_value <= 0:
        return 0.0

    drawdown = 0.0
    for position in resolved_positions:
        asset_class = map_asset_class(position.asset.asset_type, position.asset.name, position.asset.symbol)
        drawdown += (position.value / total_value) * DRAWDOWN_SCORES.get(asset_class, 0.2)
    return round(drawdown * 100.0, 1)


def fallback_volatility(asset_type: str) -> float | None:
    if asset_type == "bond":
        return 6.0
    if asset_type == "stock":
        return 24.0
    if asset_type == "etf":
        return 15.0
    if asset_type == "cash":
        return 0.0
    return None


def transform_alerts(alerts: list) -> list[PortfolioAnalyzeAlert]:
    return [
        PortfolioAnalyzeAlert(
            severity=alert.severity,
            code=alert.type.upper(),
            message=alert.message,
        )
        for alert in alerts
    ]


def transform_suggestions(suggestions: list) -> list[PortfolioAnalyzeSuggestion]:
    transformed: list[PortfolioAnalyzeSuggestion] = []
    for suggestion in suggestions:
        code = (
            suggestion.message.upper()
            .replace(" ", "_")
            .replace(",", "")
            .replace(".", "")[:48]
        )
        transformed.append(PortfolioAnalyzeSuggestion(code=code, message=suggestion.message))
    return transformed


def generate_top_insights(
    normalized_assets: list[NormalizedInsightAsset],
    metrics: PortfolioAnalyzeMetrics,
) -> list[PortfolioTopInsight]:
    geo = aggregate_geo(normalized_assets)
    underlying_holdings, contributors = aggregate_holdings(normalized_assets)
    asset_allocation = {asset_class: weight / 100.0 for asset_class, weight in metrics.asset_allocation.items()}
    drawdown = metrics.estimated_drawdown / 100.0
    equity_weight = asset_allocation.get("Equity", 0.0)

    insights: list[PortfolioTopInsight] = []

    if geo:
        dominant_region, dominant_weight = max(geo.items(), key=lambda item: item[1])
        if dominant_weight > 0.60:
            severity = "high" if dominant_weight > 0.75 else "medium"
            severity_points = 3 if severity == "high" else 2
            impact_points = 3 if dominant_weight > 0.75 else 2
            confidence_points = max(asset.geo_confidence for asset in normalized_assets) if normalized_assets else 1
            region_label = dominant_region
            insights.append(
                PortfolioTopInsight(
                    id=f"geo_{slugify(region_label)}",
                    type="geo_concentration",
                    severity=severity,
                    score=severity_points * impact_points * confidence_points,
                    title=f"Sei molto concentrato su {region_label}",
                    short_description=f"Il {format_pct(dominant_weight)} del tuo portafoglio dipende da quest'area.",
                    explanation_data={
                        "region": region_label,
                        "weight": round(dominant_weight, 4),
                    },
                    cta_label="Spiegamelo meglio",
                )
            )

    if underlying_holdings:
        top_name, top_weight = max(underlying_holdings.items(), key=lambda item: item[1])
        if top_weight > 0.08:
            severity = "high" if top_weight > 0.10 else "medium"
            severity_points = 3 if severity == "high" else 2
            impact_points = 3 if top_weight > 0.12 else 2
            confidence_points = max(asset.holdings_confidence for asset in normalized_assets) if normalized_assets else 1
            instruments = sorted(contributors.get(top_name, set()))
            insights.append(
                PortfolioTopInsight(
                    id=f"overlap_{slugify(top_name)}",
                    type="holding_overlap",
                    severity=severity,
                    score=severity_points * impact_points * confidence_points,
                    title=f"Hai una sovrapposizione forte su {top_name}",
                    short_description=(
                        f"{top_name} pesa circa il {format_pct(top_weight)} del portafoglio "
                        f"attraverso {len(instruments)} strumenti."
                    ),
                    explanation_data={
                        "holding": top_name,
                        "weight": round(top_weight, 4),
                        "instrument_count": len(instruments),
                        "instruments": instruments,
                    },
                    cta_label="Spiegamelo meglio",
                )
            )

    if drawdown > 0.18 or equity_weight > 0.75:
        severity = "high" if drawdown > 0.25 else "medium"
        severity_points = 3 if severity == "high" else 2
        impact_points = 3 if drawdown > 0.25 or equity_weight > 0.85 else 2
        confidence_points = 3 if normalized_assets else 1
        insights.append(
            PortfolioTopInsight(
                id="risk_drawdown",
                type="portfolio_risk",
                severity=severity,
                score=severity_points * impact_points * confidence_points,
                title="Il portafoglio puo oscillare piu di quanto sembri",
                short_description=(
                    f"Il drawdown stimato e circa {format_pct(drawdown)} "
                    f"con una quota equity del {format_pct(equity_weight)}."
                ),
                explanation_data={
                    "drawdown": round(drawdown, 4),
                    "equity_weight": round(equity_weight, 4),
                    "risk_score": metrics.risk_score,
                },
                cta_label="Spiegamelo meglio",
            )
        )

    insights.sort(key=lambda insight: (-insight.score, insight.title))
    return insights[:3]


def aggregate_geo(normalized_assets: list[NormalizedInsightAsset]) -> dict[str, float]:
    geo: dict[str, float] = defaultdict(float)
    for asset in normalized_assets:
        for region, weight in asset.geo_exposure.items():
            geo[region] += asset.weight * weight
    return {region: round(weight, 4) for region, weight in geo.items() if weight > 0}


def aggregate_holdings(
    normalized_assets: list[NormalizedInsightAsset],
) -> tuple[dict[str, float], dict[str, set[str]]]:
    holdings: dict[str, float] = defaultdict(float)
    contributors: dict[str, set[str]] = defaultdict(set)
    for asset in normalized_assets:
        for name, weight in asset.top_holdings.items():
            contribution = asset.weight * weight
            if contribution <= 0:
                continue
            holdings[name] += contribution
            contributors[name].add(asset.ticker)
    return (
        {name: round(weight, 4) for name, weight in holdings.items() if weight > 0},
        contributors,
    )


def build_geo_exposure(asset: CatalogAsset, enrich: dict | None) -> tuple[dict[str, float], int]:
    if enrich and enrich.get("country_weights"):
        exposure: dict[str, float] = defaultdict(float)
        for item in enrich["country_weights"]:
            region = map_country_to_region(str(item.get("name") or ""))
            exposure[region] += normalize_percentage(item.get("percentage"))
        normalized = normalize_weight_map(exposure)
        if normalized:
            return normalized, 3

    if asset.region_profile:
        exposure = {
            REGION_LABELS.get(region, region): normalize_percentage(weight)
            for region, weight in asset.region_profile.items()
            if normalize_percentage(weight) > 0
        }
        return normalize_weight_map(exposure), 2

    return {}, 1


def build_top_holdings(asset: CatalogAsset, enrich: dict | None) -> tuple[dict[str, float], int]:
    if enrich and enrich.get("top_holdings"):
        holdings = {
            str(item.get("name") or "").strip(): normalize_percentage(item.get("percentage"))
            for item in enrich["top_holdings"]
            if str(item.get("name") or "").strip()
        }
        normalized = {name: round(weight, 4) for name, weight in holdings.items() if weight > 0}
        if normalized:
            return normalized, 3

    if asset.top_holdings:
        normalized = {
            name: round(normalize_percentage(weight), 4)
            for name, weight in asset.top_holdings.items()
            if name and normalize_percentage(weight) > 0
        }
        if normalized:
            return normalized, 2

    return {}, 1


def map_asset_class(asset_type: str, name: str, symbol: str) -> str:
    normalized_type = (asset_type or "").strip().lower()
    normalized_name = f"{name} {symbol}".lower()

    if "gold" in normalized_name:
        return "Gold"
    if normalized_type in {"bond"}:
        return "Bond"
    if normalized_type in {"cash"}:
        return "Cash"
    if normalized_type in {"stock", "etf", "fund"}:
        return "Equity"
    return "Equity"


def normalize_percentage(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric > 1.0:
        return numeric / 100.0
    return numeric


def normalize_weight_map(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {name: weight for name, weight in weights.items() if weight > 0}
    total = sum(cleaned.values())
    if total <= 0:
        return {}
    return {name: round(weight / total, 4) for name, weight in cleaned.items()}


def format_pct(value: float) -> str:
    return f"{round(value * 100.0, 1):.1f}%"


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return cleaned.strip("_") or "insight"


def map_country_to_region(country_name: str) -> str:
    name = country_name.strip().lower()
    usa_names = {"united states", "usa", "us", "stati uniti", "united states of america"}
    europe_names = {
        "germany",
        "france",
        "united kingdom",
        "uk",
        "netherlands",
        "switzerland",
        "spain",
        "italy",
        "sweden",
        "denmark",
        "finland",
        "norway",
        "belgium",
        "ireland",
        "austria",
        "portugal",
        "luxembourg",
        "greece",
        "poland",
        "czech republic",
        "hungary",
        "romania",
        "croatia",
        "germania",
        "francia",
        "regno unito",
        "paesi bassi",
        "svizzera",
        "spagna",
        "italia",
        "svezia",
        "danimarca",
        "finlandia",
        "norvegia",
        "belgio",
        "irlanda",
        "austria",
        "portogallo",
        "lussemburgo",
        "grecia",
    }
    emerging_names = {
        "china",
        "india",
        "brazil",
        "taiwan",
        "south korea",
        "mexico",
        "south africa",
        "indonesia",
        "thailand",
        "malaysia",
        "philippines",
        "chile",
        "colombia",
        "peru",
        "turkey",
        "saudi arabia",
        "qatar",
        "united arab emirates",
        "egypt",
        "pakistan",
        "vietnam",
        "nigeria",
        "cina",
        "brasile",
        "corea del sud",
        "messico",
        "sudafrica",
    }
    if name in usa_names:
        return "USA"
    if name in europe_names:
        return "Europe"
    if name in emerging_names:
        return "Emerging Markets"
    return "Other"


def build_insight_explanation_template(insight: PortfolioTopInsight) -> str:
    data = insight.explanation_data

    if insight.type == "geo_concentration":
        region = str(data.get("region") or "questa area")
        weight = format_pct(float(data.get("weight") or 0))
        return (
            f"Questo insight dice che una parte molto ampia del portafoglio dipende da {region}. "
            f"Nel tuo caso parliamo di circa {weight}, quindi se quell'area attraversa una fase debole il portafoglio tende a muoversi tutto nella stessa direzione. "
            f"E' un po' come avere molte aziende diverse ma tutte collegate allo stesso motore economico. "
            "Non vuol dire che il portafoglio sia sbagliato, ma che la diversificazione geografica reale e' piu bassa di quanto sembri. "
            "Per questo l'analisi segnala la concentrazione come uno dei punti principali da capire."
        )

    if insight.type == "holding_overlap":
        holding = str(data.get("holding") or "questa societa")
        weight = format_pct(float(data.get("weight") or 0))
        instruments = int(data.get("instrument_count") or 0)
        return (
            f"Qui il punto non e' il numero di ETF o titoli che possiedi, ma quanta esposizione finale hai verso {holding}. "
            f"Stimiamo che {holding} valga circa {weight} del portafoglio complessivo, distribuito su {instruments} strumenti. "
            "Quando la stessa partecipazione compare in piu prodotti, la diversificazione apparente cresce ma quella reale molto meno. "
            "E' come comprare piu confezioni diverse che dentro contengono in parte lo stesso ingrediente. "
            "Per questo l'overlap viene evidenziato come insight separato."
        )

    drawdown = format_pct(float(data.get("drawdown") or 0))
    equity_weight = format_pct(float(data.get("equity_weight") or 0))
    return (
        f"L'analisi stima che in una fase negativa il portafoglio possa subire un calo nell'ordine di {drawdown}. "
        f"Una ragione chiave e' che la componente azionaria pesa circa {equity_weight}, quindi la sensibilita' alle oscillazioni di mercato resta elevata. "
        "Il drawdown non e' una previsione esatta del prossimo movimento, ma una misura utile per capire quanto puo essere ampia una discesa plausibile. "
        "In pratica serve a confrontare il rischio percepito con quello che il portafoglio potrebbe mostrare nei momenti difficili. "
        "Per questo il motore lo porta tra i tre insight principali."
    )


def generate_ai_explanation(config: CopilotConfig, insight: PortfolioTopInsight) -> str:
    user_prompt = (
        "Spiega questo insight ad un investitore retail italiano.\n"
        "Evita consigli operativi e resta educativo.\n"
        "Insight JSON:\n"
        f"{json.dumps(insight.model_dump(), ensure_ascii=False)}"
    )
    response = call_provider_for_text(config, EXPLAIN_SYSTEM_PROMPT, user_prompt)
    cleaned = clean_explanation_text(response)
    if cleaned:
        return cleaned
    return build_insight_explanation_template(insight)


def clean_explanation_text(value: str) -> str:
    normalized = " ".join((value or "").strip().split())
    if not normalized:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return " ".join(sentences[:5]).strip()


def call_provider_for_text(config: CopilotConfig, system_prompt: str, user_prompt: str) -> str:
    provider = config.provider
    if provider in {"openai", "openrouter", "local"}:
        import openai

        kwargs = {"api_key": config.api_key}
        if provider == "openrouter":
            kwargs["base_url"] = "https://openrouter.ai/api/v1"
        elif provider == "local":
            kwargs["base_url"] = config.local_url or "http://localhost:11434/v1"

        client = openai.OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=config.model,
            max_tokens=220,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=config.api_key)
        response = client.messages.create(
            model=config.model,
            max_tokens=220,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")

    if provider == "gemini":
        from google import genai

        client = genai.Client(api_key=config.api_key)
        response = client.models.generate_content(
            model=config.model,
            contents=[
                {"role": "user", "parts": [{"text": system_prompt}]},
                {"role": "model", "parts": [{"text": "Capito, resto educativo e semplice."}]},
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            config={"max_output_tokens": 220},
        )
        return response.text or ""

    raise ValueError(f"Unsupported provider: {provider}")


def resolve_identifier(repo: PortfolioRepository, identifier: str, catalog: dict[str, CatalogAsset]) -> CatalogAsset | None:
    key = normalize_identifier(identifier)
    db_asset = lookup_asset_in_db(repo, key)
    if db_asset is not None:
        supplement = catalog.get(normalize_identifier(db_asset.symbol)) or (catalog.get(normalize_identifier(db_asset.isin)) if db_asset.isin else None)
        if supplement is not None:
            return CatalogAsset(
                symbol=db_asset.symbol,
                isin=db_asset.isin,
                name=db_asset.name,
                asset_type=db_asset.asset_type,
                quote_currency=db_asset.quote_currency,
                estimated_volatility=supplement.estimated_volatility,
                ter=supplement.ter,
                overlap_tags=supplement.overlap_tags,
                region_profile=supplement.region_profile,
                top_holdings=supplement.top_holdings,
                asset_id=db_asset.asset_id,
            )
        return CatalogAsset(
            symbol=db_asset.symbol,
            isin=db_asset.isin,
            name=db_asset.name,
            asset_type=db_asset.asset_type,
            quote_currency=db_asset.quote_currency,
            estimated_volatility=fallback_volatility(db_asset.asset_type),
            ter=0.0 if db_asset.asset_type in {"stock", "bond", "cash"} else None,
            overlap_tags=[],
            region_profile={},
            top_holdings={},
            asset_id=db_asset.asset_id,
        )
    return catalog.get(key)


@dataclass
class DbResolvedAsset:
    asset_id: int
    symbol: str
    isin: str | None
    name: str
    asset_type: str
    quote_currency: str


def lookup_asset_in_db(repo: PortfolioRepository, identifier: str) -> DbResolvedAsset | None:
    if not getattr(repo, "engine", None):
        return None
    with repo.engine.begin() as conn:
        row = conn.execute(
            text(
                """
                select id, symbol, isin, coalesce(name, symbol) as name, asset_type, quote_currency
                from assets
                where upper(symbol) = :identifier
                   or upper(coalesce(isin, '')) = :identifier
                   or upper(split_part(symbol, '.', 1)) = :identifier
                order by id asc
                limit 1
                """
            ),
            {"identifier": identifier},
        ).mappings().first()
    if row is None:
        return None
    return DbResolvedAsset(
        asset_id=int(row["id"]),
        symbol=str(row["symbol"]),
        isin=str(row["isin"]) if row["isin"] else None,
        name=str(row["name"]),
        asset_type=str(row["asset_type"]),
        quote_currency=str(row["quote_currency"]),
    )


def normalize_identifier(value: str) -> str:
    return value.strip().upper()


@lru_cache(maxsize=1)
def load_asset_catalog() -> dict[str, CatalogAsset]:
    path = Path(__file__).resolve().parent.parent / "data" / "asset_metadata.json"
    raw_items = json.loads(path.read_text(encoding="utf-8"))
    catalog: dict[str, CatalogAsset] = {}
    for item in raw_items:
        asset = CatalogAsset(
            symbol=item["symbol"],
            isin=item.get("isin"),
            name=item["name"],
            asset_type=item["asset_type"],
            quote_currency=item["quote_currency"],
            estimated_volatility=item.get("estimated_volatility"),
            ter=item.get("ter"),
            overlap_tags=item.get("overlap_tags", []),
            region_profile=item.get("region_profile", {}),
            top_holdings=item.get("top_holdings", {}),
            asset_id=None,
        )
        catalog[normalize_identifier(asset.symbol)] = asset
        if asset.isin:
            catalog[normalize_identifier(asset.isin)] = asset
    return catalog
