"""Market headlines for the Markets tab.

Headlines come from Google News RSS in Italian, one search per market
(constants.NEWS_QUERIES): it needs no API key nor Yahoo session. When it
returns too few headlines, Yahoo's search API adds the English news of a
handful of symbols per market (constants.NEWS_SYMBOLS). yfinance's
``Ticker.news`` is not used: it needs a Yahoo cookie and crumb, which Yahoo
refuses to server IPs.

The same article is often returned for several searches: it is kept once,
under the market of the first search it was found for. The most relevant
headlines are the newest, with a cap per market so that a busy day on Wall
Street does not crowd out the other markets.
"""

import logging
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from ..constants.market_symbols import NEWS_QUERIES, NEWS_SYMBOLS
from ..models import MarketNewsItem

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
ARTICLES_PER_SOURCE = 6
MAX_SUMMARY_CHARS = 280
# Below this many headlines from Google News, Yahoo's are added.
MIN_HEADLINES = 6
_HTTP_TIMEOUT_SECONDS = 10.0
_HEADERS = {
    # Without a browser User-Agent Yahoo answers 429 regardless of traffic.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()


def fetch_market_news(
    google_fetcher: Callable[[str, str], list[MarketNewsItem]] | None = None,
    yahoo_fetcher: Callable[[str, str], list[MarketNewsItem]] | None = None,
) -> list[MarketNewsItem]:
    """The most relevant headlines across markets; an empty list when every source fails."""
    google_fetcher = google_fetcher or fetch_google_news
    yahoo_fetcher = yahoo_fetcher or fetch_yahoo_search_news

    items = _fetch_all(google_fetcher, NEWS_QUERIES)
    if len(items) < MIN_HEADLINES:
        logger.warning("Google News returned %d headlines, adding Yahoo news", len(items))
        items += _fetch_all(yahoo_fetcher, NEWS_SYMBOLS)
    if not items:
        logger.warning("No market news from Google News nor Yahoo")
    return select_relevant_news(items)


def fetch_google_news(query: str, region: str) -> list[MarketNewsItem]:
    """Italian headlines of the last two days for a Google News search."""
    params = {"q": f"{query} when:2d", "hl": "it", "gl": "IT", "ceid": "IT:it"}
    response = _client().get(GOOGLE_NEWS_RSS_URL, params=params, headers=_HEADERS, timeout=_HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return parse_google_news_rss(response.content, region)[:ARTICLES_PER_SOURCE]


def fetch_yahoo_search_news(symbol: str, region: str) -> list[MarketNewsItem]:
    """English headlines that Yahoo's search API returns for a symbol."""
    params = {"q": symbol, "quotesCount": 0, "newsCount": ARTICLES_PER_SOURCE, "enableFuzzyQuery": "false"}
    response = _client().get(YAHOO_SEARCH_URL, params=params, headers=_HEADERS, timeout=_HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    news = response.json().get("news") or []
    items = (parse_yahoo_article(article, symbol, region) for article in news[:ARTICLES_PER_SOURCE])
    return [item for item in items if item is not None]


def parse_google_news_rss(content: bytes | str, region: str | None) -> list[MarketNewsItem]:
    """Items of a Google News RSS feed. Titles end with " - <source>": the
    suffix is dropped, the source becomes the publisher."""
    root = ET.fromstring(content)
    items: list[MarketNewsItem] = []
    for entry in root.iter("item"):
        title = _clean_text(entry.findtext("title"))
        if not title:
            continue
        publisher = _clean_text(entry.findtext("source"))
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3].rstrip()
        published = _to_utc(entry.findtext("pubDate"))
        items.append(
            MarketNewsItem(
                title=title,
                publisher=publisher,
                link=_http_url(_clean_text(entry.findtext("link"))),
                published=published.isoformat() if published else None,
                related_symbol=None,
                region=region,
            )
        )
    return items


def parse_yahoo_article(article: Any, symbol: str, region: str | None) -> MarketNewsItem | None:
    """Item for a Yahoo news entry, or None without a title.

    Yahoo's search API returns the flat shape (title, publisher, link,
    providerPublishTime in epoch seconds); its news stream nests the fields
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


def _fetch_all(fetcher: Callable[[str, str], list[MarketNewsItem]], sources: list[tuple[str, str]]) -> list[MarketNewsItem]:
    def fetch_one(source: tuple[str, str]) -> list[MarketNewsItem]:
        key, region = source
        try:
            return fetcher(key, region)
        except Exception as exc:
            logger.warning("Market news fetch failed for %s (%s): %s", key, region, exc)
            return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(fetch_one, sources))
    return [item for result in results for item in result]


def _client() -> httpx.Client:
    global _http_client
    with _http_client_lock:
        if _http_client is None:
            _http_client = httpx.Client(follow_redirects=True)
        return _http_client


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
            text = value.strip()
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = parsedate_to_datetime(text)  # RSS: "Thu, 29 Oct 2026 16:45:00 GMT"
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    return None
