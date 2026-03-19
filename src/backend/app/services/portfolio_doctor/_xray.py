import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    XRayCoverageIssue,
    XRayEtfDetail,
    XRayHolding,
    XRayResponse,
)
from ._holdings import AnalyzedHolding, _load_holdings

logger = logging.getLogger(__name__)


def _resolve_isin_for_holding(repo: PortfolioRepository, holding: AnalyzedHolding) -> str | None:
    """Try to resolve the ISIN for a holding from the asset table or metadata."""
    try:
        asset = repo.get_asset(holding.asset_id)
        if asset.isin:
            return asset.isin.strip().upper()
    except (ValueError, AttributeError):
        pass

    try:
        meta = repo.get_asset_metadata(holding.asset_id)
        if meta and meta.raw_info:
            raw = meta.raw_info if isinstance(meta.raw_info, dict) else {}
            raw_isin = raw.get("isin") or raw.get("ISIN")
            if isinstance(raw_isin, str) and raw_isin.strip():
                return raw_isin.strip().upper()
    except Exception:
        pass

    return None


def compute_portfolio_xray(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str,
    finance_client: object,
    justetf_client: object = None,
) -> XRayResponse:
    holdings = _load_holdings(repo, portfolio_id, user_id)
    if not holdings:
        raise ValueError("Portafoglio non trovato o vuoto")

    # Skip obvious non-fund assets (cash) but try ALL others,
    # because many ETFs are mis-classified as "stock" in the DB.
    candidates = [h for h in holdings if h.asset_type.lower() not in {"cash"}]

    # Load justETF enrichment data for all candidates
    enrichment_map: dict[int, dict] = {}
    try:
        enrichment_map = repo.get_etf_enrichment_bulk([h.asset_id for h in candidates])
    except Exception:
        pass

    # Auto-enrich candidates missing from enrichment_map
    if justetf_client is not None:
        missing = [h for h in candidates if h.asset_id not in enrichment_map]
        for h in missing:
            isin = _resolve_isin_for_holding(repo, h)
            if not isin:
                continue
            try:
                try:
                    pricing = repo.get_asset_pricing_symbol(h.asset_id, provider="yfinance")
                    fallback_symbol = pricing.provider_symbol
                except Exception:
                    fallback_symbol = h.symbol
                data = justetf_client.fetch_profile(isin, symbol=fallback_symbol)
                repo.upsert_etf_enrichment(h.asset_id, isin, data)
                enrichment_map[h.asset_id] = data
                logger.info("Auto-enriched asset %s (ISIN %s) from justETF", h.symbol, isin)
            except Exception as exc:
                logger.debug("Auto-enrich failed for %s (ISIN %s): %s", h.symbol, isin, exc)

    # Resolve provider symbols
    provider_symbols: dict[int, str] = {}
    for h in candidates:
        try:
            pricing = repo.get_asset_pricing_symbol(h.asset_id, provider="yfinance")
            provider_symbols[h.asset_id] = pricing.provider_symbol
        except Exception:
            provider_symbols[h.asset_id] = h.symbol

    # Fetch holdings for each candidate using ThreadPoolExecutor
    # Skip candidates that already have justETF enrichment holdings
    etf_raw_holdings: dict[int, list] = {}
    yfinance_failures: dict[int, str] = {}
    needs_yfinance = [h for h in candidates if h.asset_id not in enrichment_map or not enrichment_map[h.asset_id].get("top_holdings")]

    def fetch_one(asset_id: int, symbol: str):
        return asset_id, finance_client.get_etf_top_holdings(symbol)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_one, h.asset_id, provider_symbols[h.asset_id]): h
            for h in needs_yfinance
        }
        for future in as_completed(futures):
            try:
                aid, result = future.result()
                if result:  # only keep assets that actually have holdings (= ETFs/funds)
                    etf_raw_holdings[aid] = result
                else:
                    yfinance_failures[aid] = "yfinance returned no top holdings"
            except Exception as exc:
                asset = futures[future]
                yfinance_failures[asset.asset_id] = f"yfinance holdings fetch failed: {exc}"

    # Analyze all non-cash candidates and report which ones are not covered.
    etf_holdings = candidates

    # Build per-ETF details and aggregate
    aggregated: dict[str, dict] = defaultdict(lambda: {"name": "", "weight": 0.0, "contributors": []})
    etf_details: list[XRayEtfDetail] = []
    coverage_issues: list[XRayCoverageIssue] = []
    covered_weight = 0.0
    covered_etf_count = 0

    # Aggregated country/sector from enrichment
    country_totals: dict[str, float] = {}
    sector_totals: dict[str, float] = {}

    for h in etf_holdings:
        enrich = enrichment_map.get(h.asset_id)
        is_fund_candidate = (
            h.asset_type.lower() in {"etf", "fund"}
            or (enrich is not None)
            or (h.asset_id in etf_raw_holdings)
        )
        if not is_fund_candidate and h.asset_id not in yfinance_failures:
            continue
        detail_holdings = []

        # Prefer justETF top_holdings if available
        if enrich and enrich.get("top_holdings"):
            holdings_source = "justetf"
            failure_reason = None
            for th in enrich["top_holdings"]:
                name = th.get("name", "")
                isin = th.get("isin", "")
                pct = th.get("percentage")
                if pct is None:
                    continue
                weight_frac = pct / 100.0
                contrib_weight = weight_frac * h.weight_pct
                key = isin or name  # use ISIN as key if available
                aggregated[key]["name"] = name
                aggregated[key]["weight"] += contrib_weight
                aggregated[key]["contributors"].append(h.symbol)
                detail_holdings.append(XRayHolding(
                    symbol=isin or name,
                    name=name,
                    aggregated_weight_pct=round(pct, 2),
                    etf_contributors=[h.symbol],
                ))
        elif h.asset_id in etf_raw_holdings:
            holdings_source = "yfinance"
            failure_reason = None
            raw = etf_raw_holdings[h.asset_id]
            for rh in raw:
                contrib_weight = rh.weight * h.weight_pct
                aggregated[rh.symbol]["name"] = rh.name
                aggregated[rh.symbol]["weight"] += contrib_weight
                aggregated[rh.symbol]["contributors"].append(h.symbol)
                detail_holdings.append(XRayHolding(
                    symbol=rh.symbol,
                    name=rh.name,
                    aggregated_weight_pct=round(rh.weight * 100, 2),
                    etf_contributors=[h.symbol],
                ))
        else:
            holdings_source = "missing"
            failure_reason = yfinance_failures.get(
                h.asset_id,
                "justETF enrichment missing and yfinance fallback unavailable",
            )
            coverage_issues.append(
                XRayCoverageIssue(
                    asset_id=h.asset_id,
                    symbol=h.symbol,
                    name=h.name,
                    reason=failure_reason,
                )
            )

        # Aggregate country/sector from enrichment
        if detail_holdings:
            covered_weight += h.weight_pct
            covered_etf_count += 1
        if enrich and enrich.get("country_weights"):
            for cw in enrich["country_weights"]:
                name = cw["name"]
                country_totals[name] = country_totals.get(name, 0.0) + h.weight_pct * (cw["percentage"] / 100.0)
        if enrich and enrich.get("sector_weights"):
            for sw in enrich["sector_weights"]:
                name = sw["name"]
                sector_totals[name] = sector_totals.get(name, 0.0) + h.weight_pct * (sw["percentage"] / 100.0)

        etf_details.append(XRayEtfDetail(
            asset_id=h.asset_id,
            symbol=h.symbol,
            name=h.name,
            investment_focus=enrich.get("investment_focus") if enrich else None,
            portfolio_weight_pct=round(h.weight_pct, 2),
            holdings_available=bool(detail_holdings),
            holdings_source=holdings_source,
            failure_reason=failure_reason,
            top_holdings=detail_holdings,
        ))

    # Sort aggregated by weight descending, take top 25
    sorted_agg = sorted(aggregated.items(), key=lambda x: x[1]["weight"], reverse=True)[:25]
    aggregated_holdings = [
        XRayHolding(
            symbol=sym,
            name=data["name"],
            aggregated_weight_pct=round(data["weight"], 2),
            etf_contributors=sorted(set(data["contributors"])),
        )
        for sym, data in sorted_agg
    ]

    total_portfolio_weight = sum(h.weight_pct for h in holdings)
    coverage = round(covered_weight / total_portfolio_weight * 100, 1) if total_portfolio_weight > 0 else 0.0

    # Build sorted country/sector dicts
    agg_countries = {k: round(v, 1) for k, v in sorted(country_totals.items(), key=lambda x: -x[1]) if v >= 0.1}
    agg_sectors = {k: round(v, 1) for k, v in sorted(sector_totals.items(), key=lambda x: -x[1]) if v >= 0.1}

    return XRayResponse(
        portfolio_id=portfolio_id,
        aggregated_holdings=aggregated_holdings,
        etf_details=sorted(etf_details, key=lambda x: x.portfolio_weight_pct, reverse=True),
        etf_count=covered_etf_count,
        coverage_pct=coverage,
        aggregated_country_exposure=agg_countries,
        aggregated_sector_exposure=agg_sectors,
        coverage_issues=coverage_issues,
    )
