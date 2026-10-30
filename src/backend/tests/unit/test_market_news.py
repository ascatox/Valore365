from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_markets import register_markets_routes
from app.constants import NEWS_SYMBOLS
from app.models import MarketNewsItem
from app.services.market_news import MAX_SUMMARY_CHARS, parse_yahoo_article, select_relevant_news


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


def test_news_symbols_cover_international_markets():
    regions = {region for _, region in NEWS_SYMBOLS}
    assert {"USA", "Europa", "Italia", "Asia"} <= regions


def test_news_route_merges_symbols_and_caches():
    calls = []

    def fetcher(symbol, region):
        calls.append(symbol)
        if symbol == "^GDAXI":
            return [_item("DAX slips", "2026-10-29T09:00:00+00:00", region=region, symbol=symbol)]
        if symbol == "^GSPC":
            return [_item("Wall Street opens higher", "2026-10-29T14:00:00+00:00", symbol=symbol)]
        return []

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_markets_routes(router, repo=object(), finance_client=object(), news_fetcher=fetcher)
    app.include_router(router)
    client = TestClient(app)

    payload = client.get("/api/markets/news").json()
    assert [(item["title"], item["region"]) for item in payload["items"]] == [
        ("Wall Street opens higher", "USA"),
        ("DAX slips", "Europa"),
    ]
    assert sorted(calls) == sorted(symbol for symbol, _ in NEWS_SYMBOLS)

    client.get("/api/markets/news")
    assert len(calls) == len(NEWS_SYMBOLS)
