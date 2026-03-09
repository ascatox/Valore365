from app.schemas.instant_portfolio_analyzer import InstantAnalyzeRequest, ParsedPositionInput
from app.services.instant_portfolio_analyzer import (
    analyze_public_portfolio,
    parse_raw_text,
    parse_request_positions,
    resolve_identifier,
)


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
    assert response.category_scores.diversification >= 0
    assert response.cta.show_signup is True
