import logging
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text

from ...repository import PortfolioRepository

logger = logging.getLogger(__name__)


@dataclass
class AnalyzedHolding:
    asset_id: int
    symbol: str
    name: str
    asset_type: str
    quote_currency: str
    market_value: float
    weight_pct: float


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


def _is_equity_like(holding: AnalyzedHolding) -> bool:
    return holding.asset_type.lower() in {"stock", "etf", "fund"}


def _normalize_portfolio_ids(portfolio_ids: list[int]) -> list[int]:
    normalized: list[int] = []
    for portfolio_id in portfolio_ids:
        if portfolio_id <= 0 or portfolio_id in normalized:
            continue
        normalized.append(portfolio_id)
    return normalized


def _load_aggregate_holdings(
    repo: PortfolioRepository,
    portfolio_ids: list[int],
    user_id: str,
) -> list[AnalyzedHolding]:
    holdings: list[AnalyzedHolding] = []
    for portfolio_id in portfolio_ids:
        holdings.extend(_load_holdings(repo, portfolio_id, user_id))
    return _rebalance_holdings_by_market_value(holdings)


def _rebalance_holdings_by_market_value(holdings: list[AnalyzedHolding]) -> list[AnalyzedHolding]:
    total_market_value = sum(max(0.0, holding.market_value) for holding in holdings)
    if total_market_value <= 0:
        return []

    rebalanced: list[AnalyzedHolding] = []
    for holding in holdings:
        market_value = max(0.0, holding.market_value)
        rebalanced.append(
            AnalyzedHolding(
                asset_id=holding.asset_id,
                symbol=holding.symbol,
                name=holding.name,
                asset_type=holding.asset_type,
                quote_currency=holding.quote_currency,
                market_value=market_value,
                weight_pct=(market_value / total_market_value) * 100.0,
            )
        )
    return rebalanced


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
    dates_by_asset: dict[int, list[date]] = defaultdict(list)
    for row in rows:
        close = float(row["close"])
        if close > 0 and math.isfinite(close):
            aid = int(row["asset_id"])
            prices_by_asset[aid].append(close)
            dates_by_asset[aid].append(row["price_date"])

    all_dates: set[date] = set()
    for series_dates in dates_by_asset.values():
        all_dates.update(series_dates)
    if len(all_dates) < 20:
        return 0.0, 0.0

    sorted_dates = sorted(all_dates)
    price_lookup: dict[int, dict[date, float]] = {}
    for asset_id, series_dates in dates_by_asset.items():
        price_lookup[asset_id] = {
            day: price
            for day, price in zip(series_dates, prices_by_asset[asset_id])
        }

    weight_map = {h.asset_id: h.weight_pct / 100.0 for h in holdings}
    total_weight = sum(weight_map.values())
    if total_weight <= 0:
        return 0.0, 0.0

    portfolio_values: list[float] = []
    for current_date in sorted_dates:
        value = 0.0
        for asset_id, weight in weight_map.items():
            series_prices = prices_by_asset.get(asset_id, [])
            series_dates = dates_by_asset.get(asset_id, [])
            if series_prices and series_dates:
                latest_price = series_prices[0]
                for series_date, series_price in zip(series_dates, series_prices):
                    if series_date > current_date:
                        break
                    latest_price = series_price
                base_price = series_prices[0]
                normalized_value = latest_price / base_price if base_price > 0 else 1.0
            else:
                normalized_value = 1.0
            value += normalized_value * (weight / total_weight)
        portfolio_values.append(value)

    log_returns = [
        math.log(curr / prev)
        for prev, curr in zip(portfolio_values, portfolio_values[1:])
        if prev > 0 and curr > 0
    ]
    if len(log_returns) < 20:
        return 0.0, 0.0

    mu_daily = statistics.mean(log_returns)
    sigma_daily = statistics.pstdev(log_returns)
    return mu_daily * 252, sigma_daily * math.sqrt(252)


def _percentile(sorted_values: list[float], pct: int) -> float:
    n = len(sorted_values)
    k = (pct / 100) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
