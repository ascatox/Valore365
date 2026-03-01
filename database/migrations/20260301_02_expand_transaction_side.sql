-- Feature 2: Tracking della Liquidità
-- Expand transaction side to support cash movements
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_side_check;
ALTER TABLE transactions ADD CONSTRAINT transactions_side_check
  CHECK (side IN ('buy','sell','deposit','withdrawal','dividend','fee','interest'));
ALTER TABLE transactions ALTER COLUMN asset_id DROP NOT NULL;
