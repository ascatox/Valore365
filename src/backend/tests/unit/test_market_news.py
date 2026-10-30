import httpx
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_markets import register_markets_routes
from app.constants import NEWS_QUERIES, NEWS_SYMBOLS
from app.models import MarketNewsItem
from app.services import market_news
from app.services.market_news import (
    MAX_SUMMARY_CHARS,
    fetch_google_news,
    fetch_market_news,
    fetch_yahoo_search_news,
    parse_google_news_rss,
    parse_yahoo_article,
    select_relevant_news,
)

GOOGLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Piazza Affari - Google News</title>
<item>
  <title>Piazza Affari chiude in rialzo con le banche - Il Sole 24 ORE</title>
  <link>https://news.google.com/rss/articles/abc?oc=5</link>
  <pubDate>Thu, 29 Oct 2026 16:45:00 GMT</pubDate>
  <description>&lt;a href="https://news.google.com/rss/articles/abc"&gt;...&lt;/a&gt;</description>
  <source url="https://www.ilsole24ore.com">Il Sole 24 ORE</source>
</item>
<item>
  <title>Spread Btp-Bund in calo</title>
  <link>javascript:alert(1)</link>
  <pubDate>not a date</pubDate>
</item>
<item><title> </title></item>
</channel></rss>"""


def _item(title, published, region="USA", symbol="^GSPC"):
    return MarketNewsItem(title=title, published=published, region=region, related_symbol=symbol)


def test_parse_legacy_article_in_utc():
    item = parse_yahoo_article(
        {
            "title": "  Stocks   rally ",
            "publisher": "Reuters",
            "link": "https://example.com/a",
            "providerPublishTime": 1_793_000_000,
        },
        "^GSPC",
        "USA",
    )
    assert item.title == "Stocks rally"
    assert item.publisher == "Reuters"
    assert item.link == "https://example.com/a"
    assert item.published == "2026-10-26T07:33:20+00:00"
    assert (item.related_symbol, item.region, item.summary) == ("^GSPC", "USA", None)


def test_parse_content_article():
    item = parse_yahoo_article(
        {
            "id": "x",
            "content": {
                "title": "ECB holds rates",
                "summary": "The ECB kept rates unchanged.",
                "pubDate": "2026-10-29T13:15:00Z",
                "provider": {"displayName": "Bloomberg"},
                "canonicalUrl": {"url": "https://example.com/ecb"},
            },
        },
        "^STOXX50E",
        "Europa",
    )
    assert item.title == "ECB holds rates"
    assert item.publisher == "Bloomberg"
    assert item.link == "https://example.com/ecb"
    assert item.published == "2026-10-29T13:15:00+00:00"
    assert item.summary == "The ECB kept rates unchanged."
    assert item.region == "Europa"


def test_parse_falls_back_to_click_through_url_and_drops_unsafe_links():
    article = {
        "content": {
            "title": "Gold record",
            "canonicalUrl": None,
            "clickThroughUrl": {"url": "https://example.com/gold"},
        }
    }
    assert parse_yahoo_article(article, "GC=F", "Materie prime").link == "https://example.com/gold"
    unsafe = parse_yahoo_article({"title": "x", "link": "javascript:alert(1)"}, "GC=F", None)
    assert unsafe.link is None


def test_parse_skips_articles_without_title_and_bad_dates():
    assert parse_yahoo_article({"content": {"summary": "no title"}}, "^GSPC", "USA") is None
    assert parse_yahoo_article(None, "^GSPC", "USA") is None
    assert parse_yahoo_article({"title": "t", "providerPublishTime": "yesterday"}, "^GSPC", None).published is None


def test_parse_truncates_long_summary_on_a_word():
    item = parse_yahoo_article({"title": "t", "summary": "parola " * 100}, "^GSPC", None)
    assert len(item.summary) <= MAX_SUMMARY_CHARS
    assert item.summary.endswith("parola…")


def test_select_dedupes_titles_and_sorts_newest_first():
    items = [
        _item("Old", "2026-10-28T10:00:00+00:00"),
        _item("Fed  cuts", "2026-10-29T10:00:00+00:00"),
        _item("fed cuts", "2026-10-29T11:00:00+00:00", region="Europa"),
        _item("Undated", None),
    ]
    selected = select_relevant_news(items)
    assert [item.title for item in selected] == ["Fed  cuts", "Old", "Undated"]
    assert selected[0].region == "USA"


def test_select_caps_each_region_while_others_have_news():
    us = [_item(f"US {i}", f"2026-10-29T1{i}:00:00+00:00") for i in range(6)]
    asia = [_item("Nikkei", "2026-10-28T01:00:00+00:00", region="Asia", symbol="^N225")]
    selected = select_relevant_news(us + asia, limit=4, per_region=3)
    assert [item.title for item in selected] == ["US 5", "US 4", "US 3", "Nikkei"]

    # Free slots go to the newest leftovers of a capped region.
    selected = select_relevant_news(us + asia, limit=6, per_region=3)
    assert [item.title for item in selected] == ["US 5", "US 4", "US 3", "US 2", "US 1", "Nikkei"]


def test_parse_google_news_rss():
    items = parse_google_news_rss(GOOGLE_RSS, "Italia")
    assert len(items) == 2
    first, second = items
    assert first.title == "Piazza Affari chiude in rialzo con le banche"
    assert first.publisher == "Il Sole 24 ORE"
    assert first.link == "https://news.google.com/rss/articles/abc?oc=5"
    assert first.published == "2026-10-29T16:45:00+00:00"
    assert (first.region, first.related_symbol, first.summary) == ("Italia", None, None)
    assert (second.title, second.publisher, second.link, second.published) == ("Spread Btp-Bund in calo", None, None, None)


def _mock_client(monkeypatch, handler):
    requests = []

    def record(request):
        requests.append(request)
        return handler(request)

    monkeypatch.setattr(market_news, "_client", lambda: httpx.Client(transport=httpx.MockTransport(record)))
    return requests


def test_fetch_google_news_requests_italian_recent_results(monkeypatch):
    requests = _mock_client(monkeypatch, lambda request: httpx.Response(200, content=GOOGLE_RSS.encode()))
    items = fetch_google_news("Piazza Affari", "Italia")
    assert [item.title for item in items] == ["Piazza Affari chiude in rialzo con le banche", "Spread Btp-Bund in calo"]
    params = requests[0].url.params
    assert requests[0].url.host == "news.google.com"
    assert (params["q"], params["hl"], params["gl"], params["ceid"]) == ("Piazza Affari when:2d", "it", "IT", "IT:it")
    assert "Mozilla" in requests[0].headers["user-agent"]


def test_fetch_yahoo_search_news(monkeypatch):
    payload = {
        "quotes": [],
        "news": [
            {"title": "Nikkei rises", "publisher": "Reuters", "link": "https://example.com/n", "providerPublishTime": 1_793_000_000},
            {"publisher": "no title"},
        ],
    }
    requests = _mock_client(monkeypatch, lambda request: httpx.Response(200, json=payload))
    items = fetch_yahoo_search_news("^N225", "Asia")
    assert [(item.title, item.region, item.related_symbol) for item in items] == [("Nikkei rises", "Asia", "^N225")]
    assert requests[0].url.params["q"] == "^N225"
    assert requests[0].url.params["quotesCount"] == "0"


def test_fetch_errors_raise_for_the_caller(monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(503))
    try:
        fetch_google_news("bitcoin", "Crypto")
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")


def _google_with(count):
    def fetcher(query, region):
        if region != "Italia":
            return []
        return [_item(f"Notizia {i}", f"2026-10-29T1{i}:00:00+00:00", region=region, symbol=None) for i in range(count)]

    return fetcher


def test_market_news_uses_google_news_only_when_enough():
    yahoo_calls = []
    items = fetch_market_news(_google_with(6), lambda symbol, region: yahoo_calls.append(symbol) or [])
    assert len(items) == 6
    assert yahoo_calls == []


def test_market_news_falls_back_to_yahoo_when_google_fails():
    def failing_google(query, region):
        raise httpx.ConnectError("blocked")

    calls = []

    def yahoo(symbol, region):
        calls.append(symbol)
        if symbol == "^GSPC":
            return [_item("Wall Street opens higher", "2026-10-29T14:00:00+00:00", symbol=symbol)]
        return []

    items = fetch_market_news(failing_google, yahoo)
    assert [item.title for item in items] == ["Wall Street opens higher"]
    assert sorted(calls) == sorted(symbol for symbol, _ in NEWS_SYMBOLS)


def test_news_sources_cover_international_markets():
    for sources in (NEWS_QUERIES, NEWS_SYMBOLS):
        assert {"USA", "Europa", "Italia", "Asia"} <= {region for _, region in sources}


def _news_client(fetcher):
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_markets_routes(router, repo=object(), finance_client=object(), news_fetcher=fetcher)
    app.include_router(router)
    return TestClient(app)


def test_news_route_returns_and_caches_headlines():
    calls = []

    def fetcher():
        calls.append(1)
        return [_item("DAX slips", "2026-10-29T09:00:00+00:00", region="Europa", symbol=None)]

    client = _news_client(fetcher)
    payload = client.get("/api/markets/news").json()
    assert payload["items"][0]["title"] == "DAX slips"
    assert payload["items"][0]["region"] == "Europa"
    client.get("/api/markets/news")
    assert len(calls) == 1


def test_news_route_retries_sooner_after_an_empty_result(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.api.routes_markets._time.monotonic", lambda: clock[0])
    calls = []
    client = _news_client(lambda: calls.append(1) or [])

    assert client.get("/api/markets/news").json() == {"items": []}
    clock[0] += 30
    client.get("/api/markets/news")
    assert len(calls) == 1
    clock[0] += 31
    client.get("/api/markets/news")
    assert len(calls) == 2
