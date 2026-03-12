"""Lightweight wrapper around justetf-scraping library with rate limiting."""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


class JustEtfClient:
    """Fetches ETF profile data from justETF with rate limiting and error handling."""

    def __init__(self, rate_limit_seconds: float = 2.0):
        self._rate_limit = rate_limit_seconds
        self._last_request: float = 0.0
        self._lock = threading.Lock()
        self._enabled = os.environ.get("JUSTETF_ENABLED", "true").lower() != "false"

    def _wait_rate_limit(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._rate_limit:
                time.sleep(self._rate_limit - elapsed)
            self._last_request = time.monotonic()

    def fetch_profile(self, isin: str) -> dict | None:
        """Fetch ETF profile from justETF. Returns DB-ready dict or None on error."""
        if not self._enabled:
            logger.debug("justETF client disabled via JUSTETF_ENABLED=false")
            return None

        if not isin or len(isin) != 12:
            logger.warning("Invalid ISIN for justETF lookup: %s", isin)
            return None

        try:
            self._wait_rate_limit()
            from justetf_scraping import get_etf_overview  # type: ignore

            logger.debug("Fetching justETF data for ISIN %s", isin)
            overview = get_etf_overview(isin)

            return self._convert_overview(isin, overview)
        except Exception:
            logger.warning("justETF fetch failed for ISIN %s", isin, exc_info=True)
            return None

    def _convert_overview(self, isin: str, ov: dict) -> dict:
        """Convert EtfOverview TypedDict to our DB-friendly format."""
        # Country weights
        country_weights = None
        countries = ov.get("countries")
        if countries is not None:
            try:
                if hasattr(countries, "to_dict"):
                    # pandas Series
                    country_weights = [
                        {"name": str(k), "percentage": round(float(v) * 100, 2) if float(v) <= 1.0 else round(float(v), 2)}
                        for k, v in countries.items()
                        if v and float(v) > 0
                    ]
                elif isinstance(countries, dict):
                    country_weights = [
                        {"name": str(k), "percentage": round(float(v) * 100, 2) if float(v) <= 1.0 else round(float(v), 2)}
                        for k, v in countries.items()
                        if v and float(v) > 0
                    ]
            except Exception:
                logger.debug("Could not parse country weights for %s", isin)

        # Sector weights
        sector_weights = None
        sectors = ov.get("sectors")
        if sectors is not None:
            try:
                if hasattr(sectors, "to_dict"):
                    sector_weights = [
                        {"name": str(k), "percentage": round(float(v) * 100, 2) if float(v) <= 1.0 else round(float(v), 2)}
                        for k, v in sectors.items()
                        if v and float(v) > 0
                    ]
                elif isinstance(sectors, dict):
                    sector_weights = [
                        {"name": str(k), "percentage": round(float(v) * 100, 2) if float(v) <= 1.0 else round(float(v), 2)}
                        for k, v in sectors.items()
                        if v and float(v) > 0
                    ]
            except Exception:
                logger.debug("Could not parse sector weights for %s", isin)

        # Top holdings
        top_holdings = None
        holdings = ov.get("top_holdings")
        if holdings is not None:
            try:
                if hasattr(holdings, "to_dict"):
                    # DataFrame — rows have name, percentage, maybe isin
                    rows = holdings.to_dict("records") if hasattr(holdings, "to_dict") else []
                    top_holdings = []
                    for row in rows:
                        entry: dict = {}
                        # The library returns a DataFrame with columns like 'name', 'weight'
                        if "name" in row:
                            entry["name"] = str(row["name"])
                        if "weight" in row:
                            w = float(row["weight"])
                            entry["percentage"] = round(w * 100, 2) if w <= 1.0 else round(w, 2)
                        if "isin" in row:
                            entry["isin"] = str(row["isin"])
                        if entry:
                            top_holdings.append(entry)
                elif isinstance(holdings, list):
                    top_holdings = holdings
            except Exception:
                logger.debug("Could not parse top holdings for %s", isin)

        def _safe_float(key: str) -> float | None:
            v = ov.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        def _safe_str(key: str) -> str | None:
            v = ov.get(key)
            return str(v) if v is not None else None

        return {
            "isin": isin,
            "name": _safe_str("name"),
            "description": _safe_str("description"),
            "index_tracked": _safe_str("index"),
            "investment_focus": _safe_str("investment_focus"),
            "country_weights": country_weights,
            "sector_weights": sector_weights,
            "top_holdings": top_holdings,
            "holdings_date": _safe_str("holdings_date"),
            "replication_method": _safe_str("replication"),
            "distribution_policy": _safe_str("distribution_policy"),
            "distribution_frequency": _safe_str("distribution_frequency"),
            "fund_currency": _safe_str("fund_currency"),
            "currency_hedged": ov.get("currency_hedged") if isinstance(ov.get("currency_hedged"), bool) else None,
            "domicile": _safe_str("domicile"),
            "fund_provider": _safe_str("fund_provider"),
            "fund_size_eur": _safe_float("fund_size"),
            "ter": _safe_float("ter"),
            "volatility_1y": _safe_float("volatility_1y"),
            "sustainability": ov.get("sustainability") if isinstance(ov.get("sustainability"), bool) else None,
            "inception_date": _safe_str("inception_date"),
        }
