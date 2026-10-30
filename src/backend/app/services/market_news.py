"""Market headlines for the Markets tab, from Yahoo news through yfinance.

News are fetched for a handful of symbols per region (constants.NEWS_SYMBOLS).
The same article is often returned for several symbols: it is kept once, under
the region of the first symbol it was found for. The most relevant headlines
are the newest, with a cap per region so that a busy day on Wall Street does
not crowd out the other markets.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from ..models import MarketNewsItem

ARTICLES_PER_SYMBOL = 6
MAX_SUMMARY_CHARS = 280


def parse_yahoo_article(article: Any, symbol: str, region: str | None) -> MarketNewsItem | None:
    """Item for one entry of ``yf.Ticker.news``, or None without a title.

    yfinance returns the flat legacy shape (title, publisher, link,
    providerPublishTime in epoch seconds) or, since 0.2.50, the fields nested
    under ``content`` (provider.displayName, canonicalUrl.url, pubDate in ISO).
    """
    if not isinstance(article, dict):
        return None
    content = article.get("content") if isinstance(article.get("content"), dict) else {}

    title = _clean_text(article.get("title") or content.get("title"))
    if not title:
        return None
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    publisher = _clean_text(article.get("publisher") or provider.get("displayName"))
    link = _http_url(article.get("link")) or _nested_url(content, "canonicalUrl") or _nested_url(content, "clickThroughUrl")
    published = _to_utc(article.get("providerPublishTime") or content.get("pubDate") or content.get("displayTime"))
    summary = _clean_text(article.get("summary") or content.get("summary") or content.get("description"))
    if summary and len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 1].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"

    return MarketNewsItem(
        title=title,
        publisher=publisher,
        link=link,
        published=published.isoformat() if published else None,
        related_symbol=symbol,
        region=region,
        summary=summary,
    )


def select_relevant_news(items: Iterable[MarketNewsItem], limit: int = 20, per_region: int = 4) -> list[MarketNewsItem]:
    """Newest first, without duplicate titles, at most ``per_region`` items per
    region while other regions have news; the remaining slots go to the newest
    leftovers."""
    seen_titles: set[str] = set()
    unique: list[MarketNewsItem] = []
    for item in items:
        key = " ".join(item.title.lower().split())
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(item)
    # Stable sort: items without a date keep their fetch order, after the dated ones.
    unique.sort(key=lambda item: item.published or "", reverse=True)

    picked: list[MarketNewsItem] = []
    leftovers: list[MarketNewsItem] = []
    per_region_count: dict[str | None, int] = {}
    for item in unique:
        count = per_region_count.get(item.region, 0)
        if count < per_region:
            per_region_count[item.region] = count + 1
            picked.append(item)
        else:
            leftovers.append(item)
    picked = picked[:limit]
    picked.extend(leftovers[: limit - len(picked)])
    picked.sort(key=lambda item: item.published or "", reverse=True)
    return picked


def fetch_yahoo_news(symbol: str, region: str | None) -> list[MarketNewsItem]:
    """Latest headlines for one symbol; an empty list when Yahoo fails."""
    import yfinance as yf

    try:
        raw_news = yf.Ticker(symbol).news or []
    except Exception:
        return []
    items = (parse_yahoo_article(article, symbol, region) for article in raw_news[:ARTICLES_PER_SYMBOL])
    return [item for item in items if item is not None]


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _http_url(value: Any) -> str | None:
    # Rendered as an href: anything but http(s) (e.g. javascript:) is dropped.
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return value
    return None


def _nested_url(content: dict, key: str) -> str | None:
    value = content.get(key)
    return _http_url(value.get("url")) if isinstance(value, dict) else None


def _to_utc(value: Any) -> datetime | None:
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(int(value), tz=UTC)
        if isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, OverflowError, OSError):
        return None
    return None
