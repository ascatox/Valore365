from datetime import date

from app.price_validation import (
    ValidationResult,
    check_staleness,
    validate_fx_rate,
    validate_price_bar,
    validate_quote_price,
)


class TestValidatePriceBar:
    def _bar(self, **overrides):
        defaults = dict(
            asset_id=1, symbol="AAPL", price_date=date(2026, 3, 2),
            open=100.0, high=105.0, low=95.0, close=102.0, volume=1000,
        )
        defaults.update(overrides)
        return defaults

    def test_valid_bar(self):
        vr = validate_price_bar(**self._bar())
        assert vr.valid
        assert vr.warnings == []
        assert vr.rejected_reason is None

    def test_reject_zero_close(self):
        vr = validate_price_bar(**self._bar(close=0))
        assert not vr.valid
        assert "close=0" in vr.rejected_reason

    def test_reject_negative_open(self):
        vr = validate_price_bar(**self._bar(open=-1.0))
        assert not vr.valid
        assert "open=-1.0" in vr.rejected_reason

    def test_reject_negative_high(self):
        vr = validate_price_bar(**self._bar(high=-5.0))
        assert not vr.valid

    def test_reject_negative_low(self):
        vr = validate_price_bar(**self._bar(low=-0.01))
        assert not vr.valid

    def test_reject_high_less_than_low(self):
        vr = validate_price_bar(**self._bar(high=90.0, low=95.0))
        assert not vr.valid
        assert "high=90.0 < low=95.0" in vr.rejected_reason

    def test_warn_large_spread(self):
        vr = validate_price_bar(**self._bar(high=300.0, low=100.0, open=100.0, close=100.0), max_ohlc_spread_pct=100.0)
        assert vr.valid
        assert any("ohlc_spread" in w for w in vr.warnings)

    def test_warn_spike_vs_previous_close(self):
        vr = validate_price_bar(**self._bar(close=200.0), previous_close=100.0, max_daily_change_pct=50.0)
        assert vr.valid
        assert any("daily_change" in w for w in vr.warnings)

    def test_no_spike_warning_within_threshold(self):
        vr = validate_price_bar(**self._bar(close=104.0), previous_close=100.0, max_daily_change_pct=50.0)
        assert vr.valid
        assert vr.warnings == []

    def test_warn_open_outside_range(self):
        vr = validate_price_bar(**self._bar(open=110.0, high=105.0, low=95.0))
        assert vr.valid
        assert any("open=110.0 outside" in w for w in vr.warnings)


class TestValidateQuotePrice:
    def test_valid_price(self):
        vr = validate_quote_price(asset_id=1, symbol="AAPL", price=100.5)
        assert vr.valid

    def test_reject_zero_price(self):
        vr = validate_quote_price(asset_id=1, symbol="AAPL", price=0.0)
        assert not vr.valid
        assert "price=0.0" in vr.rejected_reason

    def test_reject_negative_price(self):
        vr = validate_quote_price(asset_id=1, symbol="AAPL", price=-5.0)
        assert not vr.valid

    def test_reject_at_min_price(self):
        vr = validate_quote_price(asset_id=1, symbol="AAPL", price=0.0001, min_price=0.0001)
        assert not vr.valid

    def test_accept_above_min_price(self):
        vr = validate_quote_price(asset_id=1, symbol="AAPL", price=0.001, min_price=0.0001)
        assert vr.valid


class TestValidateFxRate:
    def test_valid_rate(self):
        vr = validate_fx_rate(from_ccy="USD", to_ccy="EUR", price_date=date(2026, 3, 2), rate=0.92)
        assert vr.valid

    def test_reject_zero_rate(self):
        vr = validate_fx_rate(from_ccy="USD", to_ccy="EUR", price_date=date(2026, 3, 2), rate=0.0)
        assert not vr.valid

    def test_reject_negative_rate(self):
        vr = validate_fx_rate(from_ccy="USD", to_ccy="EUR", price_date=date(2026, 3, 2), rate=-1.0)
        assert not vr.valid

    def test_reject_rate_above_max(self):
        vr = validate_fx_rate(from_ccy="USD", to_ccy="EUR", price_date=date(2026, 3, 2), rate=20000.0, max_rate=10000.0)
        assert not vr.valid

    def test_reject_rate_below_min(self):
        vr = validate_fx_rate(from_ccy="USD", to_ccy="EUR", price_date=date(2026, 3, 2), rate=0.00001, min_rate=0.0001)
        assert not vr.valid


class TestCheckStaleness:
    def test_not_stale(self):
        assert not check_staleness(asset_id=1, symbol="AAPL", price_date=date(2026, 3, 2), today=date(2026, 3, 3), stale_days=5)

    def test_stale(self):
        assert check_staleness(asset_id=1, symbol="AAPL", price_date=date(2026, 2, 20), today=date(2026, 3, 3), stale_days=5)

    def test_none_price_date_is_stale(self):
        assert check_staleness(asset_id=1, symbol="AAPL", price_date=None, today=date(2026, 3, 3), stale_days=5)

    def test_exactly_at_threshold_not_stale(self):
        assert not check_staleness(asset_id=1, symbol="AAPL", price_date=date(2026, 2, 26), today=date(2026, 3, 3), stale_days=5)

    def test_one_day_over_threshold_is_stale(self):
        assert check_staleness(asset_id=1, symbol="AAPL", price_date=date(2026, 2, 25), today=date(2026, 3, 3), stale_days=5)
