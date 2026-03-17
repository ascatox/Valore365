"""Lightweight wrapper around justetf-scraping library with rate limiting."""

import logging
import os
import threading
import time

from .errors import ProviderError

logger = logging.getLogger(__name__)


class JustEtfClient:
    """Fetches ETF profile data from justETF with rate limiting and error handling."""

    def __init__(self, rate_limit_seconds: float = 2.0, blocked_cooldown_seconds: float | None = None):
        self._rate_limit = rate_limit_seconds
        self._last_request: float = 0.0
        self._lock = threading.Lock()
        self._enabled = os.environ.get("JUSTETF_ENABLED", "true").lower() != "false"
        self._blocked_until: float = 0.0
        self._blocked_cooldown_seconds = blocked_cooldown_seconds
        if self._blocked_cooldown_seconds is None:
            self._blocked_cooldown_seconds = float(os.environ.get("JUSTETF_BLOCKED_COOLDOWN_SECONDS", "900"))

    @staticmethod
    def _is_forbidden_error(exc: Exception) -> bool:
        return "status 403" in str(exc).lower()

    def _get_blocked_remaining_seconds(self) -> float:
        return max(0.0, self._blocked_until - time.monotonic())

    def _activate_block_cooldown(self) -> None:
        self._blocked_until = time.monotonic() + max(0.0, self._blocked_cooldown_seconds)

    def _wait_rate_limit(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._rate_limit:
                time.sleep(self._rate_limit - elapsed)
            self._last_request = time.monotonic()

    def fetch_profile(self, isin: str, max_retries: int = 3) -> dict | None:
        """Fetch ETF profile from justETF. Returns DB-ready dict or None on error."""
        if not self._enabled:
            raise ProviderError(
                provider="justetf",
                operation="fetch_profile",
                symbol=isin,
                reason="disabled",
                message="justETF client disabled via JUSTETF_ENABLED=false",
            )

        blocked_remaining = self._get_blocked_remaining_seconds()
        if blocked_remaining > 0:
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
                overview = get_etf_overview(isin)
                return self._convert_overview(isin, overview)
            except Exception as exc:
                if self._is_forbidden_error(exc):
                    self._activate_block_cooldown()
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
