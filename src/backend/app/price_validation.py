from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    valid: bool = True
    warnings: list[str] = field(default_factory=list)
    rejected_reason: str | None = None


def validate_price_bar(
    *,
    asset_id: int,
    symbol: str,
    price_date: date,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    previous_close: float | None = None,
    max_daily_change_pct: float = 50.0,
    max_ohlc_spread_pct: float = 100.0,
) -> ValidationResult:
    result = ValidationResult()

    # Reject: any OHLC value <= 0
    for label, val in [("open", open), ("high", high), ("low", low), ("close", close)]:
        if val <= 0:
            result.valid = False
            result.rejected_reason = f"{label}={val} <= 0"
            logger.warning(
                "price_bar_rejected asset_id=%s symbol=%s date=%s reason=%s",
                asset_id, symbol, price_date, result.rejected_reason,
            )
            return result

    # Reject: high < low
    if high < low:
        result.valid = False
        result.rejected_reason = f"high={high} < low={low}"
        logger.warning(
            "price_bar_rejected asset_id=%s symbol=%s date=%s reason=%s",
            asset_id, symbol, price_date, result.rejected_reason,
        )
        return result

    # Warn: OHLC spread too large
    if low > 0:
        spread_pct = ((high - low) / low) * 100
        if spread_pct > max_ohlc_spread_pct:
            msg = f"ohlc_spread={spread_pct:.1f}% > {max_ohlc_spread_pct}%"
            result.warnings.append(msg)
            logger.warning(
                "price_bar_warning asset_id=%s symbol=%s date=%s warning=%s",
                asset_id, symbol, price_date, msg,
            )

    # Warn: spike vs previous close
    if previous_close is not None and previous_close > 0:
        change_pct = abs(close - previous_close) / previous_close * 100
        if change_pct > max_daily_change_pct:
            msg = f"daily_change={change_pct:.1f}% > {max_daily_change_pct}%"
            result.warnings.append(msg)
            logger.warning(
                "price_bar_warning asset_id=%s symbol=%s date=%s warning=%s",
                asset_id, symbol, price_date, msg,
            )

    # Warn: open or close outside high-low range
    for label, val in [("open", open), ("close", close)]:
        if val > high or val < low:
            msg = f"{label}={val} outside [low={low}, high={high}]"
            result.warnings.append(msg)
            logger.warning(
                "price_bar_warning asset_id=%s symbol=%s date=%s warning=%s",
                asset_id, symbol, price_date, msg,
            )

    return result


def validate_quote_price(
    *,
    asset_id: int,
    symbol: str,
    price: float,
    min_price: float = 0.0001,
) -> ValidationResult:
    result = ValidationResult()
    if price <= min_price:
        result.valid = False
        result.rejected_reason = f"price={price} <= min_price={min_price}"
        logger.warning(
            "quote_rejected asset_id=%s symbol=%s reason=%s",
            asset_id, symbol, result.rejected_reason,
        )
    return result


def validate_fx_rate(
    *,
    from_ccy: str,
    to_ccy: str,
    price_date: date,
    rate: float,
    min_rate: float = 0.0001,
    max_rate: float = 10000.0,
) -> ValidationResult:
    result = ValidationResult()
    if rate <= 0:
        result.valid = False
        result.rejected_reason = f"rate={rate} <= 0"
    elif rate < min_rate or rate > max_rate:
        result.valid = False
        result.rejected_reason = f"rate={rate} outside [{min_rate}, {max_rate}]"

    if not result.valid:
        logger.warning(
            "fx_rate_rejected pair=%s/%s date=%s reason=%s",
            from_ccy, to_ccy, price_date, result.rejected_reason,
        )
    return result


def check_staleness(
    *,
    asset_id: int,
    symbol: str,
    price_date: date | None,
    today: date,
    stale_days: int = 5,
) -> bool:
    if price_date is None:
        logger.warning("price_stale asset_id=%s symbol=%s reason=no_price_date", asset_id, symbol)
        return True
    delta = (today - price_date).days
    if delta > stale_days:
        logger.warning(
            "price_stale asset_id=%s symbol=%s price_date=%s days_old=%s stale_days=%s",
            asset_id, symbol, price_date, delta, stale_days,
        )
        return True
    return False
