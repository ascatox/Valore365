import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..constants.market_symbols import MARKET_SYMBOLS, NEWS_SYMBOLS
from ..models import (
    AssetInfoPricePoint,
    AssetInfoResponse,
    ErrorResponse,
    MarketCategory,
    MarketIntradayPoint,
    MarketNewsItem,
    MarketNewsResponse,
    MarketQuoteItem,
    MarketQuotesResponse,
)
from ..repository import PortfolioRepository


def register_markets_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    finance_client: object,
) -> None:
    MARKET_QUOTES_CACHE_TTL_SECONDS = 60.0
    _market_quotes_cache: dict[str, Any] = {"payload": None, "expires_at": 0.0}
    _market_quotes_cache_lock = threading.Lock()

    MARKET_NEWS_CACHE_TTL_SECONDS = 300.0  # 5 minutes
    _market_news_cache: dict[str, Any] = {"payload": None, "expires_at": 0.0}
    _market_news_cache_lock = threading.Lock()

    @router.get("/markets/quotes", response_model=MarketQuotesResponse)
    def get_market_quotes(_auth: AuthContext = Depends(require_auth_rate_limited)) -> MarketQuotesResponse:
        now = _time.monotonic()
        with _market_quotes_cache_lock:
            cached_payload = _market_quotes_cache.get("payload")
            cached_expires = float(_market_quotes_cache.get("expires_at", 0.0) or 0.0)
            if cached_payload is not None and cached_expires > now:
                return cached_payload

        def fetch_one(symbol: str, name: str) -> MarketQuoteItem:
            try:
                mq = finance_client.get_market_quote(symbol)
                change: float | None = None
                change_pct: float | None = None
                if mq.price is not None and mq.previous_close is not None and mq.previous_close != 0:
                    change = mq.price - mq.previous_close
                    change_pct = (change / mq.previous_close) * 100

                intraday: list[MarketIntradayPoint] = []
                try:
                    bars = finance_client.get_intraday_bars(symbol)
                    intraday = [
                        MarketIntradayPoint(
                            time=b.ts.strftime('%d/%m %H:%M'),
                            price=b.close,
                        )
                        for b in bars
                    ]
                except Exception:
                    pass

                return MarketQuoteItem(
                    symbol=symbol,
                    name=name,
                    price=mq.price,
                    previous_close=mq.previous_close,
                    change=round(change, 4) if change is not None else None,
                    change_pct=round(change_pct, 4) if change_pct is not None else None,
                    ts=mq.ts,
                    error=None if mq.price is not None else "Prezzo non disponibile",
                    intraday=intraday,
                    price_source=getattr(mq, "source", None),
                    is_realtime=getattr(mq, "is_realtime", True),
                    is_fallback=getattr(mq, "is_fallback", False),
                    stale=getattr(mq, "stale", False),
                    warning=getattr(mq, "warning", None),
                )
            except Exception as exc:
                return MarketQuoteItem(
                    symbol=symbol,
                    name=name,
                    error=str(exc),
                    is_realtime=False,
                    is_fallback=True,
                    stale=True,
                    warning="market quote fetch failed",
                )

        categories: list[MarketCategory] = []
        for cat_key, cat_info in MARKET_SYMBOLS.items():
            symbol_items = cat_info["symbols"]
            with ThreadPoolExecutor(max_workers=min(4, len(symbol_items))) as executor:
                items = list(executor.map(lambda item: fetch_one(item[0], item[1]), symbol_items))
            categories.append(MarketCategory(category=cat_key, label=cat_info["label"], items=items))

        response = MarketQuotesResponse(categories=categories)
        with _market_quotes_cache_lock:
            _market_quotes_cache["payload"] = response
            _market_quotes_cache["expires_at"] = _time.monotonic() + MARKET_QUOTES_CACHE_TTL_SECONDS
        return response

    @router.get("/markets/news", response_model=MarketNewsResponse)
    def get_market_news(_auth: AuthContext = Depends(require_auth_rate_limited)) -> MarketNewsResponse:
        now = _time.monotonic()
        with _market_news_cache_lock:
            cached_payload = _market_news_cache.get("payload")
            cached_expires = float(_market_news_cache.get("expires_at", 0.0) or 0.0)
            if cached_payload is not None and cached_expires > now:
                return cached_payload

        import yfinance as yf

        seen_titles: set[str] = set()
        news_items: list[MarketNewsItem] = []

        def fetch_news(symbol: str) -> list[MarketNewsItem]:
            items: list[MarketNewsItem] = []
            try:
                ticker = yf.Ticker(symbol)
                raw_news = ticker.news or []
                for article in raw_news[:5]:
                    title = article.get("title") or article.get("content", {}).get("title", "")
                    if not title:
                        continue
                    publisher = article.get("publisher") or article.get("content", {}).get("provider", {}).get("displayName")
                    link = article.get("link") or article.get("content", {}).get("canonicalUrl", {}).get("url")
                    pub_date = article.get("providerPublishTime") or article.get("content", {}).get("pubDate")
                    pub_str = None
                    if pub_date is not None:
                        try:
                            if isinstance(pub_date, (int, float)):
                                pub_str = datetime.fromtimestamp(int(pub_date)).isoformat()
                            else:
                                pub_str = str(pub_date)
                        except Exception:
                            pass
                    items.append(MarketNewsItem(
                        title=title,
                        publisher=publisher,
                        link=link,
                        published=pub_str,
                        related_symbol=symbol,
                    ))
            except Exception:
                pass
            return items

        with ThreadPoolExecutor(max_workers=min(4, len(NEWS_SYMBOLS))) as executor:
            results = list(executor.map(fetch_news, NEWS_SYMBOLS))

        for result in results:
            for item in result:
                title_key = item.title.strip().lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    news_items.append(item)

        # Sort by publish date descending (newest first)
        news_items.sort(key=lambda x: x.published or "", reverse=True)
        news_items = news_items[:20]

        response = MarketNewsResponse(items=news_items)
        with _market_news_cache_lock:
            _market_news_cache["payload"] = response
            _market_news_cache["expires_at"] = _time.monotonic() + MARKET_NEWS_CACHE_TTL_SECONDS
        return response

    @router.get("/markets/symbol-info", response_model=AssetInfoResponse, responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}})
    def get_market_symbol_info(symbol: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetInfoResponse:
        """Return detailed info for a market symbol (index, commodity, crypto, etc.)."""
        try:
            info = finance_client.get_asset_info(symbol)
        except Exception as exc:
            raise AppError(code="provider_error", message=f"Impossibile ottenere info: {exc}", status_code=502) from exc
        price_history: list[AssetInfoPricePoint] = []
        price_history_status = "available"
        try:
            start_5y = date.today().replace(year=date.today().year - 5).isoformat()
            bars = finance_client.get_daily_bars(symbol, start_date=start_5y, end_date=date.today().isoformat())
            price_history = [
                AssetInfoPricePoint(date=b.day.isoformat(), close=b.close)
                for i, b in enumerate(bars)
                if i % 5 == 0 or i == len(bars) - 1
            ]
            if not price_history:
                price_history_status = "empty"
        except Exception as exc:
            price_history_status = f"unavailable:{exc.__class__.__name__}"
        day_change_pct: float | None = None
        if info.current_price is not None and info.previous_close is not None and info.previous_close != 0:
            day_change_pct = round(((info.current_price / info.previous_close) - 1) * 100, 2)
        return AssetInfoResponse(
            asset_id=0,
            symbol=symbol,
            name=info.name,
            asset_type=None,
            quote_type=info.quote_type,
            sector=info.sector,
            industry=info.industry,
            country=info.country,
            market_cap=info.market_cap,
            trailing_pe=info.trailing_pe,
            forward_pe=info.forward_pe,
            dividend_yield=info.dividend_yield,
            beta=info.beta,
            fifty_two_week_high=info.fifty_two_week_high,
            fifty_two_week_low=info.fifty_two_week_low,
            avg_volume=info.avg_volume,
            currency=info.currency,
            current_price=info.current_price,
            previous_close=info.previous_close,
            day_change_pct=day_change_pct,
            description=info.description,
            price_history_5y=price_history,
            expense_ratio=info.expense_ratio,
            fund_family=info.fund_family,
            total_assets=info.total_assets,
            category=info.category,
            dividend_rate=info.dividend_rate,
            profit_margins=info.profit_margins,
            return_on_equity=info.return_on_equity,
            revenue_growth=info.revenue_growth,
            earnings_growth=info.earnings_growth,
            website=info.website,
            current_price_source=info.current_price_source,
            metadata_status=info.metadata_status,
            price_history_status=price_history_status,
            warnings=info.warnings,
        )
