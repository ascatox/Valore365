"""Lightweight wrapper around justetf-scraping library with rate limiting."""

import logging
import os
import threading
import time
from typing import Any

import httpx

from .config import Settings
from .errors import ProviderError

logger = logging.getLogger(__name__)


class JustEtfClient:
    """Fetches ETF profile data from justETF with rate limiting and error handling."""

    def __init__(
        self,
        rate_limit_seconds: float = 2.0,
        blocked_cooldown_seconds: float | None = None,
        settings: Settings | None = None,
    ):
        resolved_settings = settings
        self._rate_limit = rate_limit_seconds
        self._last_request: float = 0.0
        self._lock = threading.Lock()
        self._enabled = (
            resolved_settings.justetf_enabled
            if resolved_settings is not None
            else os.environ.get("JUSTETF_ENABLED", "true").lower() != "false"
        )
        self._blocked_until: float = 0.0
        self._blocked_cooldown_seconds = blocked_cooldown_seconds
        if self._blocked_cooldown_seconds is None:
            self._blocked_cooldown_seconds = (
                resolved_settings.justetf_blocked_cooldown_seconds
                if resolved_settings is not None
                else float(os.environ.get("JUSTETF_BLOCKED_COOLDOWN_SECONDS", "900"))
            )
        self._fmp_api_key = (
            resolved_settings.fmt_api_key.strip()
            if resolved_settings is not None
            else os.environ.get("FMT_API_KEY", os.environ.get("FMP_API_KEY", "")).strip()
        )
        self._fmp_base_url = (
            resolved_settings.fmt_api_base_url.rstrip("/")
            if resolved_settings is not None
            else os.environ.get("FMT_API_BASE_URL", os.environ.get("FMP_API_BASE_URL", "https://financialmodelingprep.com/stable")).rstrip("/")
        )
        self._fmp_timeout_seconds = (
            resolved_settings.fmt_timeout_seconds
            if resolved_settings is not None
            else float(os.environ.get("FMT_TIMEOUT_SECONDS", os.environ.get("FMP_TIMEOUT_SECONDS", "10")))
        )

    @staticmethod
    def _is_forbidden_error(exc: Exception) -> bool:
        return "status 403" in str(exc).lower()

    def _get_blocked_remaining_seconds(self) -> float:
        return max(0.0, self._blocked_until - time.monotonic())

    def _activate_block_cooldown(self) -> None:
        self._blocked_until = time.monotonic() + max(0.0, self._blocked_cooldown_seconds)

    def _can_use_fmp_fallback(self, symbol: str | None) -> bool:
        return bool(self._fmp_api_key and (symbol or "").strip())

    def _wait_rate_limit(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._rate_limit:
                time.sleep(self._rate_limit - elapsed)
            self._last_request = time.monotonic()

    @staticmethod
    def _load_overview(get_etf_overview, isin: str):
        # We do not use live gettex quotes. Disabling them also avoids a current
        # upstream NameError regression in justetf-scraping.
        try:
            return get_etf_overview(isin, include_gettex=False)
        except TypeError as exc:
            if "include_gettex" not in str(exc):
                raise
            return get_etf_overview(isin)

    @staticmethod
    def _pick(data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = data.get(key)
            if value not in (None, "", []):
                return value
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _request_fmp_json(self, path: str, symbol: str) -> Any:
        response = httpx.get(
            f"{self._fmp_base_url}{path}",
            params={"symbol": symbol, "apikey": self._fmp_api_key},
            timeout=self._fmp_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("Error Message"):
            raise ProviderError(
                provider="fmp",
                operation=path.strip("/"),
                symbol=symbol,
                reason="provider_error",
                message=str(payload["Error Message"]),
            )
        return payload

    def _normalize_fmp_weight_items(self, payload: Any, *, name_keys: tuple[str, ...]) -> list[dict] | None:
        rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
        result: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = self._pick(row, *name_keys)
            percentage = self._to_float(self._pick(row, "weightPercentage", "percentage", "weightPercent", "weight"))
            if name is None or percentage is None:
                continue
            result.append({"name": str(name), "percentage": round(percentage, 2)})
        return result or None

    def _normalize_fmp_holdings(self, payload: Any) -> list[dict] | None:
        rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
        result: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = self._pick(row, "name", "asset", "holdingName", "securityName")
            percentage = self._to_float(self._pick(row, "weightPercentage", "percentage", "weightPercent", "weight"))
            holding: dict[str, Any] = {}
            if name is not None:
                holding["name"] = str(name)
            if percentage is not None:
                holding["percentage"] = round(percentage, 2)
            isin = self._pick(row, "isin", "ISIN")
            if isin is not None:
                holding["isin"] = str(isin)
            if holding:
                result.append(holding)
        return result or None

    def _fetch_profile_from_fmp(self, symbol: str) -> dict:
        symbol_value = symbol.strip().upper()
        if not symbol_value:
            raise ProviderError(
                provider="fmp",
                operation="etf_profile",
                symbol=symbol,
                reason="invalid_symbol",
                message="FMP fallback requires a valid symbol",
            )
        if not self._fmp_api_key:
            raise ProviderError(
                provider="fmp",
                operation="etf_profile",
                symbol=symbol_value,
                reason="misconfigured",
                message="FMP_API_KEY non configurata",
            )

        info_payload: Any = None
        holdings_payload: Any = None
        sectors_payload: Any = None
        countries_payload: Any = None

        for path in (
            "/etf/info",
            "/etf/holdings",
            "/etf/sector-weightings",
            "/etf/country-weightings",
        ):
            try:
                payload = self._request_fmp_json(path, symbol_value)
                if path == "/etf/info":
                    info_payload = payload
                elif path == "/etf/holdings":
                    holdings_payload = payload
                elif path == "/etf/sector-weightings":
                    sectors_payload = payload
                elif path == "/etf/country-weightings":
                    countries_payload = payload
            except Exception as exc:
                logger.info("FMP fallback request failed symbol=%s path=%s error=%s", symbol_value, path, exc)

        info_rows = info_payload if isinstance(info_payload, list) else [info_payload] if isinstance(info_payload, dict) else []
        info = info_rows[0] if info_rows and isinstance(info_rows[0], dict) else {}

        country_weights = self._normalize_fmp_weight_items(countries_payload, name_keys=("country", "name"))
        sector_weights = self._normalize_fmp_weight_items(sectors_payload, name_keys=("sector", "name"))
        top_holdings = self._normalize_fmp_holdings(holdings_payload)

        result = {
            "name": self._pick(info, "name", "fundName", "etfName"),
            "description": self._pick(info, "description", "summary"),
            "index_tracked": self._pick(info, "benchmark", "index", "indexTracked"),
            "investment_focus": self._pick(info, "investmentFocus", "assetExposure"),
            "country_weights": country_weights,
            "sector_weights": sector_weights,
            "top_holdings": top_holdings,
            "holdings_date": self._pick(info, "holdingsDate", "date"),
            "replication_method": self._pick(info, "replicationMethod", "replication"),
            "distribution_policy": self._pick(info, "distributionPolicy"),
            "distribution_frequency": self._pick(info, "distributionFrequency"),
            "fund_currency": self._pick(info, "currency", "fundCurrency"),
            "currency_hedged": self._pick(info, "currencyHedged"),
            "domicile": self._pick(info, "domicile", "fundDomicile"),
            "fund_provider": self._pick(info, "issuer", "provider", "fundProvider"),
            "fund_size_eur": self._to_float(self._pick(info, "totalAssets", "aum", "assetsUnderManagement")),
            "ter": self._to_float(self._pick(info, "expenseRatio", "ter")),
            "volatility_1y": self._to_float(self._pick(info, "volatility1Y", "volatility_1y")),
            "sustainability": self._pick(info, "sustainability"),
            "inception_date": self._pick(info, "inceptionDate"),
            "source": "fmp",
        }

        if not any(result.get(key) for key in ("name", "country_weights", "sector_weights", "top_holdings", "ter", "fund_provider")):
            raise ProviderError(
                provider="fmp",
                operation="etf_profile",
                symbol=symbol_value,
                reason="no_data",
                message=f"FMP fallback returned no ETF enrichment data for {symbol_value}",
            )
        return result

    def fetch_profile(self, isin: str, symbol: str | None = None, max_retries: int = 3) -> dict | None:
        """Fetch ETF profile from justETF. Returns DB-ready dict or None on error."""
        if not self._enabled:
            if self._can_use_fmp_fallback(symbol):
                logger.info("justETF disabled, using FMP fallback for symbol %s", symbol)
                return self._fetch_profile_from_fmp(str(symbol))
            raise ProviderError(
                provider="justetf",
                operation="fetch_profile",
                symbol=isin,
                reason="disabled",
                message="justETF client disabled via JUSTETF_ENABLED=false",
            )

        blocked_remaining = self._get_blocked_remaining_seconds()
        if blocked_remaining > 0:
            if self._can_use_fmp_fallback(symbol):
                logger.info("justETF temporarily blocked, using FMP fallback for symbol %s", symbol)
                return self._fetch_profile_from_fmp(str(symbol))
            raise ProviderError(
                provider="justetf",
                operation="fetch_profile",
                symbol=isin,
                reason="temporarily_blocked",
                message=(
                    "justETF is temporarily blocked after recent HTTP 403 responses; "
                    f"retry after about {int(blocked_remaining)}s"
                ),
                retryable=True,
            )

        if not isin or len(isin) != 12:
            raise ProviderError(
                provider="justetf",
                operation="fetch_profile",
                symbol=isin,
                reason="invalid_isin",
                message=f"Invalid ISIN for justETF lookup: {isin}",
            )

        from justetf_scraping import get_etf_overview  # type: ignore

        for attempt in range(max_retries):
            try:
                self._wait_rate_limit()
                logger.debug("Fetching justETF data for ISIN %s (attempt %d)", isin, attempt + 1)
                overview = self._load_overview(get_etf_overview, isin)
                return self._convert_overview(isin, overview)
            except Exception as exc:
                if self._is_forbidden_error(exc):
                    self._activate_block_cooldown()
                    if self._can_use_fmp_fallback(symbol):
                        logger.warning(
                            "justETF returned HTTP 403 for ISIN %s; using FMP fallback for symbol %s",
                            isin,
                            symbol,
                        )
                        return self._fetch_profile_from_fmp(str(symbol))
                    logger.warning(
                        "justETF returned HTTP 403 for ISIN %s; suspending enrichment fetches for %.0fs",
                        isin,
                        self._blocked_cooldown_seconds,
                    )
                    raise ProviderError(
                        provider="justetf",
                        operation="fetch_profile",
                        symbol=isin,
                        reason="temporarily_blocked",
                        message=(
                            "justETF returned HTTP 403 and appears to be blocking scraping requests; "
                            "enrichment fetches have been temporarily suspended"
                        ),
                        retryable=True,
                    ) from exc
                if attempt < max_retries - 1:
                    backoff = self._rate_limit * (2 ** attempt)
                    logger.info("justETF fetch failed for ISIN %s, retrying in %.1fs", isin, backoff)
                    time.sleep(backoff)
                else:
                    if self._can_use_fmp_fallback(symbol):
                        logger.warning(
                            "justETF fetch failed for ISIN %s after %d attempts; using FMP fallback for symbol %s",
                            isin,
                            max_retries,
                            symbol,
                        )
                        return self._fetch_profile_from_fmp(str(symbol))
                    logger.warning("justETF fetch failed for ISIN %s after %d attempts", isin, max_retries, exc_info=True)
                    raise ProviderError(
                        provider="justetf",
                        operation="fetch_profile",
                        symbol=isin,
                        reason="provider_error",
                        message=f"justETF fetch failed for ISIN {isin}: {exc}",
                        retryable=False,
                    ) from exc
        raise ProviderError(
            provider="justetf",
            operation="fetch_profile",
            symbol=isin,
            reason="provider_error",
            message=f"justETF fetch failed for ISIN {isin}",
        )

    @staticmethod
    def _parse_allocation_list(items) -> list[dict] | None:
        """Parse country/sector allocation data from the library.

        The library returns list[AllocationItem] dicts with keys
        ``name`` and ``percentage`` (already on a 0-100 scale).
        """
        if items is None:
            return None
        try:
            result: list[dict] = []
            if isinstance(items, list):
                for item in items:
                    name = item.get("name") if isinstance(item, dict) else None
                    pct = item.get("percentage") if isinstance(item, dict) else None
                    if name is not None and pct is not None and float(pct) > 0:
                        result.append({"name": str(name), "percentage": round(float(pct), 2)})
            elif isinstance(items, dict):
                for k, v in items.items():
                    if v and float(v) > 0:
                        result.append({"name": str(k), "percentage": round(float(v), 2)})
            elif hasattr(items, "to_dict"):
                for k, v in items.items():
                    if v and float(v) > 0:
                        result.append({"name": str(k), "percentage": round(float(v), 2)})
            return result if result else None
        except Exception:
            return None

    @staticmethod
    def _parse_holdings_list(holdings) -> list[dict] | None:
        """Parse top holdings data from the library.

        The library returns list[HoldingItem] dicts with keys
        ``name``, ``percentage``, and optionally ``isin``.
        """
        if holdings is None:
            return None
        try:
            if isinstance(holdings, list):
                result: list[dict] = []
                for item in holdings:
                    if not isinstance(item, dict):
                        continue
                    entry: dict = {}
                    if "name" in item:
                        entry["name"] = str(item["name"])
                    if "percentage" in item:
                        entry["percentage"] = round(float(item["percentage"]), 2)
                    if "isin" in item:
                        entry["isin"] = str(item["isin"])
                    if entry:
                        result.append(entry)
                return result if result else None
            return None
        except Exception:
            return None

    def _convert_overview(self, isin: str, ov: dict) -> dict:
        """Convert EtfOverview TypedDict to our DB-friendly format."""
        country_weights = self._parse_allocation_list(ov.get("countries"))
        sector_weights = self._parse_allocation_list(ov.get("sectors"))
        top_holdings = self._parse_holdings_list(ov.get("top_holdings"))

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
            "domicile": _safe_str("fund_domicile"),
            "fund_provider": _safe_str("fund_provider"),
            "fund_size_eur": _safe_float("fund_size_eur"),
            "ter": _safe_float("ter"),
            "volatility_1y": _safe_float("volatility_1y"),
            "sustainability": ov.get("sustainability") if isinstance(ov.get("sustainability"), bool) else None,
            "inception_date": _safe_str("inception_date"),
        }
