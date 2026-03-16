-- Add previous_close column to price_ticks for accurate daily variation calculation
alter table price_ticks add column if not exists previous_close numeric(28,10);
