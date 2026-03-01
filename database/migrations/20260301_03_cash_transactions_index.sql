-- Feature 2: Tracking della Liquidità - index for cash movements
CREATE INDEX IF NOT EXISTS idx_tx_cash_movements
  ON transactions(portfolio_id, trade_at) WHERE asset_id IS NULL;
