import logging
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from ...repository import PortfolioRepository
from ...schemas.portfolio_doctor import (
    XRayCoverageIssue,
    XRayEtfDetail,
    XRayHolding,
    XRayResponse,
)
from ._holdings import (
    AnalyzedHolding,
    PortfolioRef,
    _load_holdings,
    holding_asset_class,
    holding_classification,
    resolve_doctor_scope,
)

_NO_LOOK_THROUGH_CLASSES = {"gold", "commodity", "crypto"}

# TASK-48: the share of a distribution (countries, sectors) that no source
# attributes to a named country/sector. Every distribution sums to 100 over
# COVERAGE_DENOMINATOR with this bucket made explicit.
UNCLASSIFIED_LABEL = "Non classificato"
# Non-equity positions without country/sector data are shown under their asset
# class (shared classifier) instead of disappearing from the distribution.
ASSET_CLASS_BUCKET_LABELS: dict[str, str] = {
    "bond": "Obbligazioni (asset class)",
    "gold": "Oro (asset class)",
    "commodity": "Materie prime (asset class)",
    "crypto": "Cripto (asset class)",
    "cash": "Monetario (asset class)",
}
COVERAGE_DENOMINATOR = (
    "Valore di mercato delle posizioni del portafoglio, liquidità esclusa (saldo di cassa e "
    "posizioni di tipo cash): coperture ed esposizioni geografiche/settoriali sono in % di questo totale."
)
_HOLDINGS_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y")

logger = logging.getLogger(__name__)

# A fund's constituents change quarterly at best, so an hour is conservative.
_TOP_HOLDINGS_TTL_SECONDS = 3600.0
_TOP_HOLDINGS_MAX_ENTRIES = 2048


class _TopHoldingsCache:
    """Expiring per-symbol cache of ETF constituents, negatives included.

    Yahoo was asked about every non-cash holding on every /xray request, and
    the answer for anything that is not a fund is an empty list — re-fetched
    forever. Entries are shared process-wide because they are market data, not
    per-user data, and a per-symbol lock keeps a burst to one fetch each.
    """

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        # symbol -> (monotonic time, wall-clock epoch seconds, result)
        self._entries: dict[str, tuple[float, float, list]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, symbol: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(symbol, threading.Lock())

    def get_or_fetch(self, symbol: str, fetch) -> list:
        return self.get_or_fetch_timed(symbol, fetch)[0]

    def get_or_fetch_timed(self, symbol: str, fetch) -> tuple[list, float]:
        """Result plus the wall-clock time (epoch seconds) it was fetched at.

        The fetch time is the reference date of Yahoo data in the X-Ray
        output: Yahoo gives no as-of date for a fund's top holdings.
        """
        now = time.monotonic()
        with self._guard:
            entry = self._entries.get(symbol)
            if entry is not None and now - entry[0] < self.ttl:
                return entry[2], entry[1]

        with self._lock_for(symbol):
            # Another thread may have filled this slot while we queued.
            now = time.monotonic()
            with self._guard:
                entry = self._entries.get(symbol)
                if entry is not None and now - entry[0] < self.ttl:
                    return entry[2], entry[1]

            result = fetch()
            fetched_at = time.time()

            with self._guard:
                for stale in [s for s, (at, _, _) in self._entries.items() if now - at >= self.ttl]:
                    self._entries.pop(stale, None)
                    self._locks.pop(stale, None)
                while len(self._entries) >= self.max_entries:
                    oldest = next(iter(self._entries))
                    self._entries.pop(oldest, None)
                    self._locks.pop(oldest, None)
                self._entries[symbol] = (time.monotonic(), fetched_at, result)
            return result, fetched_at

    def clear(self) -> None:
        with self._guard:
            self._entries.clear()
            self._locks.clear()


_top_holdings_cache = _TopHoldingsCache(_TOP_HOLDINGS_TTL_SECONDS, _TOP_HOLDINGS_MAX_ENTRIES)


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
    portfolio_id: PortfolioRef,
    user_id: str,
    finance_client: object,
    justetf_client: object = None,
) -> XRayResponse:
    """X-Ray of one portfolio (int) or of several read as one (list)."""
    scope_ref, identity = resolve_doctor_scope(repo, portfolio_id, user_id)
    holdings = _load_holdings(repo, scope_ref, user_id)
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

    # Resolve provider symbols in one query rather than one connection per asset.
    provider_symbols: dict[int, str] = {}
    try:
        resolved = repo.get_asset_pricing_symbols(
            [h.asset_id for h in candidates], provider="yfinance"
        )
    except Exception:
        resolved = {}
    for h in candidates:
        pricing = resolved.get(h.asset_id)
        provider_symbols[h.asset_id] = pricing.provider_symbol if pricing else h.symbol

    # Fetch holdings for each candidate using ThreadPoolExecutor
    # Skip candidates that already have justETF enrichment holdings
    etf_raw_holdings: dict[int, list] = {}
    yfinance_failures: dict[int, str] = {}
    # Gold/commodity/crypto products (shared classifier) have no basket of
    # securities to look through: no Yahoo call, an explicit coverage reason.
    no_look_through: dict[int, str] = {}
    for h in candidates:
        asset_class = holding_asset_class(h)
        if asset_class in _NO_LOOK_THROUGH_CLASSES:
            no_look_through[h.asset_id] = (
                f"asset class {asset_class}: no underlying securities to look through"
            )
    needs_yfinance = [
        h for h in candidates
        if h.asset_id not in no_look_through
        and (h.asset_id not in enrichment_map or not enrichment_map[h.asset_id].get("top_holdings"))
    ]

    # Every non-cash holding is treated as a fund candidate, so without a cache
    # a portfolio of ordinary shares re-asks Yahoo about every one of them on
    # every request and gets the same empty answer each time. The cache keeps
    # those empty answers too, which is the whole point.
    def fetch_one(asset_id: int, symbol: str):
        return asset_id, _top_holdings_cache.get_or_fetch_timed(
            symbol, lambda: finance_client.get_etf_top_holdings(symbol)
        )

    yahoo_fetched_at: dict[int, float] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_one, h.asset_id, provider_symbols[h.asset_id]): h
            for h in needs_yfinance
        }
        for future in as_completed(futures):
            try:
                aid, (result, fetched_at) = future.result()
                if result:  # only keep assets that actually have holdings (= ETFs/funds)
                    etf_raw_holdings[aid] = result
                    yahoo_fetched_at[aid] = fetched_at
                else:
                    yfinance_failures[aid] = "yfinance returned no top holdings"
            except Exception as exc:
                asset = futures[future]
                yfinance_failures[asset.asset_id] = f"yfinance holdings fetch failed: {exc}"

    # TASK-48: denominator of every coverage/exposure metric = the non-cash
    # positions (the cash balance is not a position at all).
    denominator_weight = sum(max(0.0, h.weight_pct) for h in candidates)

    def share_of(h: AnalyzedHolding) -> float:
        if denominator_weight <= 0:
            return 0.0
        return max(0.0, h.weight_pct) / denominator_weight * 100.0

    classifications = {h.asset_id: holding_classification(h) for h in candidates}
    direct_stock_ids = {
        h.asset_id
        for h in candidates
        if classifications[h.asset_id].asset_class == "equity"
        and not classifications[h.asset_id].is_exchange_traded_product
        and h.asset_type.lower() not in {"etf", "fund"}
        and h.asset_id not in enrichment_map
        and h.asset_id not in etf_raw_holdings
    }
    # Country/sector of single shares from yFinance metadata, when stored.
    stock_metadata: dict = {}
    if direct_stock_ids:
        try:
            loaded = repo.get_asset_metadata_bulk(sorted(direct_stock_ids))
            if isinstance(loaded, dict):
                stock_metadata = loaded
        except Exception:
            stock_metadata = {}

    # Analyze all non-cash candidates and report which ones are not covered.
    etf_holdings = candidates

    # Build per-ETF details and aggregate
    aggregated: dict[str, dict] = defaultdict(lambda: {"name": "", "weight": 0.0, "contributors": []})
    etf_details: list[XRayEtfDetail] = []
    coverage_issues: list[XRayCoverageIssue] = []
    covered_weight = 0.0
    covered_etf_count = 0

    # Country/sector distributions over the denominator (sum to 100).
    country_totals: dict[str, float] = defaultdict(float)
    sector_totals: dict[str, float] = defaultdict(float)
    classified_country = 0.0
    classified_sector = 0.0
    lookthrough_share = 0.0
    funds_with_holdings_share = 0.0

    for h in etf_holdings:
        enrich = enrichment_map.get(h.asset_id)
        share = share_of(h)
        asset_class = classifications[h.asset_id].asset_class
        fallback_bucket = ASSET_CLASS_BUCKET_LABELS.get(asset_class, UNCLASSIFIED_LABEL)
        is_direct_stock = h.asset_id in direct_stock_ids

        if is_direct_stock:
            meta = stock_metadata.get(h.asset_id)
            country_items = _single_label(getattr(meta, "country", None))
            sector_items = _single_label(getattr(meta, "sector", None))
        else:
            country_items = (enrich or {}).get("country_weights") or []
            sector_items = (enrich or {}).get("sector_weights") or []
        classified_country += _spread(country_totals, country_items, share, fallback_bucket)
        classified_sector += _spread(sector_totals, sector_items, share, fallback_bucket)

        is_fund_candidate = (
            h.asset_type.lower() in {"etf", "fund"}
            or (enrich is not None)
            or (h.asset_id in etf_raw_holdings)
        )
        if is_direct_stock:
            # A single share is its own underlying holding.
            lookthrough_share += share
        if (
            not is_fund_candidate
            and h.asset_id not in yfinance_failures
            and h.asset_id not in no_look_through
        ):
            continue
        detail_holdings = []
        listed_pct = 0.0
        dates: list[tuple[date, str]] = []

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
                listed_pct += float(pct)
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
                listed_pct += rh.weight * 100.0
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
            fetched = yahoo_fetched_at.get(h.asset_id)
            if fetched is not None:
                dates.append((datetime.fromtimestamp(fetched, tz=timezone.utc).date(), "fetch_time"))
        else:
            holdings_source = "missing"
            failure_reason = no_look_through.get(h.asset_id) or yfinance_failures.get(
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

        justetf_used = bool(enrich) and (
            holdings_source == "justetf" or bool(country_items) or bool(sector_items)
        ) and not is_direct_stock
        if justetf_used:
            dates.append(_justetf_reference_date(enrich))

        if detail_holdings:
            covered_weight += h.weight_pct
            covered_etf_count += 1
            funds_with_holdings_share += share
            lookthrough_share += share * min(max(listed_pct, 0.0), 100.0) / 100.0

        if holdings_source == "justetf":
            data_source = "justetf"
        elif holdings_source == "yfinance":
            data_source = "yahoo"
        elif justetf_used:
            data_source = "justetf"
        else:
            data_source = "none"
        oldest = min(dates, key=lambda d: d[0]) if dates else None

        if detail_holdings:
            kind = "fund"
        elif is_direct_stock:
            kind = "direct_stock"
        elif h.asset_id in no_look_through:
            kind = "no_lookthrough"
        else:
            kind = "missing"

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
            lookthrough_kind=kind,
            listed_holdings_pct=round(listed_pct, 2) if detail_holdings else None,
            data_source=data_source,
            data_as_of=oldest[0].isoformat() if oldest else None,
            data_as_of_basis=oldest[1] if oldest else None,
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

    agg_countries = _finalize_distribution(country_totals)
    agg_sectors = _finalize_distribution(sector_totals)

    dated = [d.data_as_of for d in etf_details if d.data_as_of]
    data_as_of = min(dated) if dated else None

    lookthrough_pct = _pct(lookthrough_share)
    funds_pct = _pct(funds_with_holdings_share)
    country_pct = _pct(classified_country)
    sector_pct = _pct(classified_sector)

    return XRayResponse(
        **identity,
        aggregated_holdings=aggregated_holdings,
        etf_details=sorted(etf_details, key=lambda x: x.portfolio_weight_pct, reverse=True),
        etf_count=covered_etf_count,
        coverage_pct=coverage,
        aggregated_country_exposure=agg_countries,
        aggregated_sector_exposure=agg_sectors,
        coverage_issues=coverage_issues,
        lookthrough_coverage_pct=lookthrough_pct,
        funds_with_holdings_pct=funds_pct,
        classified_country_pct=country_pct,
        classified_sector_pct=sector_pct,
        unclassified_country_pct=agg_countries.get(UNCLASSIFIED_LABEL, 0.0),
        unclassified_sector_pct=agg_sectors.get(UNCLASSIFIED_LABEL, 0.0),
        coverage_denominator=COVERAGE_DENOMINATOR,
        coverage_note=_coverage_note(
            has_positions=denominator_weight > 0,
            lookthrough_pct=lookthrough_pct,
            funds_pct=funds_pct,
            country_pct=country_pct,
            sector_pct=sector_pct,
            data_as_of=data_as_of,
        ),
        data_as_of=data_as_of,
    )


# --- TASK-48 helpers -----------------------------------------------------------------


def _pct(value: float) -> float:
    return round(min(max(value, 0.0), 100.0), 1)


def _single_label(value) -> list[dict]:
    """A single country/sector (direct share) as a one-item 100% distribution."""
    if isinstance(value, str) and value.strip():
        return [{"name": value.strip(), "percentage": 100.0}]
    return []


def _spread(totals: dict[str, float], items, share: float, fallback: str) -> float:
    """Add one position's distribution to ``totals``; return the classified part.

    Provider weights are in % of the position. What they leave out (weights
    summing below 100) goes to UNCLASSIFIED_LABEL; weights summing above 100
    (provider rounding) are scaled down. Without any weight the whole position
    goes to ``fallback`` (its asset-class bucket, or UNCLASSIFIED_LABEL).
    """
    if share <= 0:
        return 0.0
    listed: list[tuple[str, float]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        pct = item.get("percentage")
        if not isinstance(name, str) or not name.strip() or not isinstance(pct, (int, float)) or pct <= 0:
            continue
        listed.append((name.strip(), float(pct)))
    total = sum(pct for _, pct in listed)
    if total <= 0:
        totals[fallback] += share
        return 0.0
    scale = 100.0 / total if total > 100.0 else 1.0
    classified = 0.0
    for name, pct in listed:
        amount = share * pct * scale / 100.0
        totals[name] += amount
        classified += amount
    rest = share - classified
    if rest > 1e-9:
        totals[UNCLASSIFIED_LABEL] += rest
    return classified


def _finalize_distribution(totals: dict[str, float]) -> dict[str, float]:
    """Round to 2 decimals so the buckets sum to exactly 100 (residual on the largest)."""
    rounded = {k: round(v, 2) for k, v in totals.items() if round(v, 2) > 0}
    if not rounded:
        return {}
    residual = round(100.0 - sum(rounded.values()), 2)
    if residual:
        largest = max(rounded, key=lambda k: rounded[k])
        rounded[largest] = round(rounded[largest] + residual, 2)
    return dict(sorted(rounded.items(), key=lambda kv: -kv[1]))


def _parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in _HOLDINGS_DATE_FORMATS:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _justetf_reference_date(enrich: dict) -> tuple[date, str]:
    """As-of date of a justETF profile: the provider's holdings date, else when it was stored."""
    stated = _parse_date(enrich.get("holdings_date"))
    if stated is not None:
        return stated, "holdings_date"
    fetched = _parse_date(enrich.get("fetched_at"))
    if fetched is not None:
        return fetched, "fetched_at"
    # Profile fetched during this request (auto-enrich): stored just now.
    return datetime.now(timezone.utc).date(), "fetched_at"


def _fmt_it(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _coverage_note(
    *,
    has_positions: bool,
    lookthrough_pct: float,
    funds_pct: float,
    country_pct: float,
    sector_pct: float,
    data_as_of: str | None,
) -> str:
    if not has_positions:
        return "Nessuna posizione esclusa la liquidità: niente da scomporre."
    note = (
        f"Scomposto il {_fmt_it(lookthrough_pct)}% del portafoglio (liquidità esclusa) nei titoli "
        f"sottostanti: peso di ogni fondo × quota del fondo coperta dalle top holdings note, più i "
        f"titoli singoli. Il {_fmt_it(funds_pct)}% è in fondi con almeno una top holding nota "
        f"(coverage_pct), ma le top holdings coprono solo parte di ciascun fondo. "
        f"Paese noto per il {_fmt_it(country_pct)}%, settore per il {_fmt_it(sector_pct)}%: "
        f"il resto è '{UNCLASSIFIED_LABEL}' o indicato per asset class (oro, obbligazioni, ...)."
    )
    if data_as_of:
        day = date.fromisoformat(data_as_of).strftime("%d/%m/%Y")
        note += f" Dati del provider aggiornati al {day} (data più vecchia fra i fondi)."
    else:
        note += " Nessun dato del provider disponibile."
    return note
