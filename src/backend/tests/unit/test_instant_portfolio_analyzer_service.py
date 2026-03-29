from app.schemas.instant_portfolio_analyzer import InstantAnalyzeRequest, ParsedPositionInput
from app.services.instant_portfolio_analyzer import (
    InstantInsightExplainUnavailable,
    analyze_public_portfolio,
    explain_public_insight,
    parse_raw_text,
    parse_request_positions,
    resolve_identifier,
)
from app.schemas.instant_portfolio_analyzer import PortfolioTopInsight


class _FakeRepo:
    engine = None


def test_parse_raw_text_returns_positions_and_line_errors():
    positions, errors = parse_raw_text("VWCE 10000\nBAD\nAGGH xyz\nEIMI 2500")

    assert len(positions) == 2
    assert positions[0][0].identifier == "VWCE"
    assert positions[0][0].value == 10000
    assert errors[0].line == 2
    assert errors[1].error == "Invalid numeric value"


def test_parse_raw_text_rejects_invalid_identifier_format():
    positions, errors = parse_raw_text("VW/CE 10000")

    assert not positions
    assert errors[0].error == "Invalid identifier format"


def test_parse_request_positions_for_text_mode():
    positions, errors = parse_request_positions(
        InstantAnalyzeRequest(
            input_mode="text",
            positions=[ParsedPositionInput(identifier=" vwce ", value=10000)],
        )
    )

    assert not errors
    assert positions[0][0].identifier == "VWCE"


def test_resolve_identifier_uses_local_catalog_without_db():
    resolved = resolve_identifier(_FakeRepo(), "IE00BK5BQT80", {})
    assert resolved is None

    from app.services.instant_portfolio_analyzer import load_asset_catalog

    resolved = resolve_identifier(_FakeRepo(), "IE00BK5BQT80", load_asset_catalog())

    assert resolved is not None
    assert resolved.symbol == "VWCE"
    assert resolved.asset_type == "etf"


def test_analyze_public_portfolio_uses_catalog_and_generates_score():
    response = analyze_public_portfolio(
        _FakeRepo(),
        InstantAnalyzeRequest(
            input_mode="raw_text",
            raw_text="VWCE 10000\nAGGH 5000\nEIMI 2000",
        ),
    )

    assert response.summary.total_value == 17000
    assert response.summary.score > 0
    assert len(response.positions) == 3
    assert response.metrics.max_position_weight > 50
    assert response.metrics.asset_allocation["Equity"] > 60
    assert response.metrics.estimated_drawdown > 0
    assert response.category_scores.diversification >= 0
    assert len(response.insights) >= 1
    assert response.cta.show_signup is True


def test_explain_public_insight_raises_when_ai_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.services.instant_portfolio_analyzer.resolve_copilot_config", lambda settings: None)

    try:
        explain_public_insight(
            PortfolioTopInsight(
                id="geo_usa",
                type="geo_concentration",
                severity="high",
                score=27,
                title="Sei molto concentrato su USA",
                short_description="Il 78% del tuo portafoglio dipende da quest'area.",
                explanation_data={"region": "USA", "weight": 0.78},
                cta_label="Spiegamelo meglio",
            )
        )
    except InstantInsightExplainUnavailable as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected AI explain to fail when copilot is unavailable")


def test_explain_public_insight_returns_ai_response(monkeypatch):
    monkeypatch.setattr("app.services.instant_portfolio_analyzer.resolve_copilot_config", lambda settings: object())
    monkeypatch.setattr(
        "app.services.instant_portfolio_analyzer.generate_ai_explanation",
        lambda config, insight: "Questa spiegazione arriva dal modello AI.",
    )

    response = explain_public_insight(
        PortfolioTopInsight(
            id="geo_usa",
            type="geo_concentration",
            severity="high",
            score=27,
            title="Sei molto concentrato su USA",
            short_description="Il 78% del tuo portafoglio dipende da quest'area.",
            explanation_data={"region": "USA", "weight": 0.78},
            cta_label="Spiegamelo meglio",
        )
    )

    assert response.insight_id == "geo_usa"
    assert response.source == "ai"
    assert "AI" in response.explanation
