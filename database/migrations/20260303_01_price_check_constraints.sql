-- Price data quality: CHECK constraints on price_bars_1d and price_ticks
-- Pre-check: clean up any existing invalid rows before adding constraints

BEGIN;

-- Remove invalid rows from price_bars_1d (zero/negative OHLC or high < low)
DELETE FROM price_bars_1d
WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0 OR high < low;

-- Remove invalid rows from price_ticks (zero/negative last)
DELETE FROM price_ticks
WHERE last <= 0;

-- Add CHECK constraints
ALTER TABLE price_bars_1d
  ADD CONSTRAINT chk_price_bars_open_positive CHECK (open > 0),
  ADD CONSTRAINT chk_price_bars_high_positive CHECK (high > 0),
  ADD CONSTRAINT chk_price_bars_low_positive  CHECK (low > 0),
  ADD CONSTRAINT chk_price_bars_close_positive CHECK (close > 0),
  ADD CONSTRAINT chk_price_bars_high_gte_low  CHECK (high >= low);

ALTER TABLE price_ticks
  ADD CONSTRAINT chk_price_ticks_last_positive CHECK (last > 0);

COMMIT;
