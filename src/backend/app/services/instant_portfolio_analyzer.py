import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from ..repository import PortfolioRepository
from ..schemas.instant_portfolio_analyzer import (
    InstantAnalyzeCta,
    InstantAnalyzeLineError,
    InstantAnalyzeRequest,
    InstantAnalyzeResponse,
    InstantAnalyzeUnresolvedItem,
    ParsedPositionInput,
    PortfolioAnalyzeAlert,
    PortfolioAnalyzeMetrics,
    PortfolioAnalyzeSuggestion,
    PortfolioAnalyzeSummary,
    ResolvedPosition,
)
from ..schemas.portfolio_doctor import PortfolioHealthMetrics
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
    asset_id: int | None = None


@dataclass
class ResolvedCatalogPosition:
    identifier: str
    value: float
    line: int | None
    raw: str | None
    asset: CatalogAsset


def analyze_public_portfolio(repo: PortfolioRepository, payload: InstantAnalyzeRequest) -> InstantAnalyzeResponse:
    normalized_positions, parse_errors = parse_request_positions(payload)
    resolved_positions, unresolved = resolve_positions(repo, normalized_positions)

    if not resolved_positions:
        raise ValueError("No valid positions found")

    total_value = round(sum(position.value for position in resolved_positions), 2)
    holdings = build_analyzed_holdings(resolved_positions, total_value)
    metrics = compute_public_metrics(resolved_positions, holdings)
    category_scores = compute_category_scores(
        metrics,
        top3_weight=round(sum(holding.weight_pct for holding in holdings[:3]), 2),
        equity_weight=round(sum(holding.weight_pct for holding in holdings if holding.asset_type in {"stock", "etf", "fund"}), 2),
    )
    score = compute_total_score(category_scores)
    summary = build_summary(metrics, category_scores)
    alerts = transform_alerts(build_alerts(metrics))
    suggestions = transform_suggestions(
        build_suggestions(
            metrics,
            equity_weight=round(sum(holding.weight_pct for holding in holdings if holding.asset_type in {"stock", "etf", "fund"}), 2),
        )
    )

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
            max_position_weight=metrics.max_position_weight,
            overlap_score=metrics.overlap_score,
            portfolio_volatility=metrics.portfolio_volatility,
            weighted_ter=metrics.weighted_ter,
        ),
        alerts=alerts,
        suggestions=suggestions,
        cta=InstantAnalyzeCta(
            show_signup=True,
            message="Create a free account to save and track this portfolio over time.",
        ),
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

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            errors.append(InstantAnalyzeLineError(line=line_number, raw=raw_line, error="Expected format: IDENTIFIER VALUE"))
            continue

        identifier = parts[0].strip().upper()
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
) -> PortfolioHealthMetrics:
    geographic_exposure = compute_geographic_exposure_with_catalog(resolved_positions, holdings)
    max_position_weight = compute_max_position_weight(holdings)
    overlap_score = compute_overlap_score(holdings)
    portfolio_volatility = compute_portfolio_volatility_from_catalog(resolved_positions)
    weighted_ter = compute_weighted_ter_from_catalog(resolved_positions)

    return PortfolioHealthMetrics(
        geographic_exposure=geographic_exposure,
        max_position_weight=max_position_weight,
        overlap_score=overlap_score,
        portfolio_volatility=portfolio_volatility,
        weighted_ter=weighted_ter,
    )


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
            asset_id=None,
        )
        catalog[normalize_identifier(asset.symbol)] = asset
        if asset.isin:
            catalog[normalize_identifier(asset.isin)] = asset
    return catalog
