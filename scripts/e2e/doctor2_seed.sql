-- Portfolio Doctor 2.0 — dati E2E (docs/doctor2/test-report.md).
-- Utente dev ("dev-user", auth Clerk disattivata), due portafogli EUR:
--   Parent (V = 685.000 €, esempio numerico PRD): VWRA 319.210 € (46,6%),
--          AGGH 205.500 €, oro fisico SGLD 95.900 €, ETF tematico con indice
--          non riconosciuto THEM 64.390 € (copertura geografica parziale);
--   Wealth: VWRA 100.000 € e EIMI 50.000 € con quotazione FERMA (30 giorni).
-- Le date sono relative a current_date, così lo script è riproducibile.
-- Prezzi in EUR (nessun cambio necessario); nessuna policy precaricata.

begin;

insert into portfolios (id, name, base_currency, owner_user_id, cash_balance)
values (1, 'Parent', 'EUR', 'dev-user', 5000),
       (2, 'Wealth', 'EUR', 'dev-user', 2500);
select setval('portfolios_id_seq', 2);

insert into assets (id, symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin)
values
  (1, 'VWRA', 'Vanguard FTSE All-World UCITS ETF (USD) Accumulating', 'etf', 'LSE', 'London Stock Exchange', 'EUR', 'IE00BK5BQT80'),
  (2, 'AGGH', 'iShares Core Global Aggregate Bond UCITS ETF EUR Hedged (Acc)', 'etf', 'MIL', 'Borsa Italiana', 'EUR', 'IE00BDBRDM35'),
  (3, 'SGLD', 'Invesco Physical Gold ETC', 'etf', 'MIL', 'Borsa Italiana', 'EUR', 'IE00B579F325'),
  (4, 'THEM', 'Thematic Frontier Opportunities UCITS ETF', 'etf', 'XETRA', 'Xetra', 'EUR', 'LU9999999991'),
  (5, 'EIMI', 'iShares Core MSCI EM IMI UCITS ETF (Acc)', 'etf', 'MIL', 'Borsa Italiana', 'EUR', 'IE00BKM4GZ66');
select setval('assets_id_seq', 5);

insert into asset_provider_symbols (asset_id, provider, provider_symbol)
values (1, 'yfinance', 'VWRA.L'), (2, 'yfinance', 'AGGH.MI'), (3, 'yfinance', 'SGLD.MI'),
       (4, 'yfinance', 'THEM.DE'), (5, 'yfinance', 'EIMI.MI');

-- TER noti (justETF) per i fondi principali; THEM ed EIMI senza scheda.
insert into etf_enrichment (asset_id, isin, name, index_tracked, investment_focus, ter, country_weights, source)
values
  (1, 'IE00BK5BQT80', 'Vanguard FTSE All-World UCITS ETF (USD) Accumulating', 'FTSE All-World', 'Equity, World',
   0.22, '[{"name":"United States","percentage":62.0},{"name":"Japan","percentage":5.5},{"name":"United Kingdom","percentage":3.5},{"name":"China","percentage":2.8},{"name":"Other","percentage":26.2}]'::jsonb, 'justetf'),
  (2, 'IE00BDBRDM35', 'iShares Core Global Aggregate Bond UCITS ETF EUR Hedged (Acc)', 'Bloomberg Global Aggregate (EUR Hedged)', 'Bonds, World, Aggregate',
   0.10, null, 'justetf'),
  (3, 'IE00B579F325', 'Invesco Physical Gold ETC', 'Gold', 'Precious Metals, Gold',
   0.12, null, 'justetf');

-- Acquisti (prezzo di carico) e depositi di cassa.
insert into transactions (portfolio_id, asset_id, side, trade_at, quantity, price, fees, trade_currency, owner_user_id)
values
  (1, null, 'deposit', current_date - 400, 1, 600000, 0, 'EUR', 'dev-user'),
  (1, 1, 'buy', current_date - 380, 2500, 100.00, 0, 'EUR', 'dev-user'),
  (1, 2, 'buy', current_date - 370, 41100, 5.10, 0, 'EUR', 'dev-user'),
  (1, 3, 'buy', current_date - 360, 500, 160.00, 0, 'EUR', 'dev-user'),
  (1, 4, 'buy', current_date - 350, 1000, 60.00, 0, 'EUR', 'dev-user'),
  (2, null, 'deposit', current_date - 300, 1, 150000, 0, 'EUR', 'dev-user'),
  (2, 1, 'buy', current_date - 290, 783.1835, 110.00, 0, 'EUR', 'dev-user'),
  (2, 5, 'buy', current_date - 280, 1500, 31.00, 0, 'EUR', 'dev-user');

-- Chiusure giornaliere: VWRA 127,684 → 2.500 × 127,684 = 319.210 €.
insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close)
values
  (1, 'yfinance', current_date - 1, 127.10, 127.90, 126.80, 127.30),
  (1, 'yfinance', current_date,     127.30, 128.00, 127.00, 127.684),
  (2, 'yfinance', current_date - 1, 5.00, 5.02, 4.98, 4.99),
  (2, 'yfinance', current_date,     4.99, 5.01, 4.98, 5.00),
  (3, 'yfinance', current_date - 1, 190.0, 192.0, 189.5, 190.9),
  (3, 'yfinance', current_date,     190.9, 192.3, 190.1, 191.80),
  (4, 'yfinance', current_date - 1, 64.0, 64.6, 63.8, 64.20),
  (4, 'yfinance', current_date,     64.2, 64.5, 64.0, 64.39),
  -- EIMI: ultima quotazione 30 giorni fa → price_stale (e oltre max_data_age_days).
  (5, 'yfinance', current_date - 31, 33.1, 33.4, 32.9, 33.20),
  (5, 'yfinance', current_date - 30, 33.2, 33.5, 33.0, 33.33);

-- Ultima sincronizzazione dei prezzi riuscita (stato dati "ok" salvo EIMI).
insert into market_data_sync_runs (trigger, status, started_at, finished_at, assets_requested, assets_updated)
values ('scheduler', 'success', now() - interval '20 minutes', now() - interval '19 minutes', 5, 4);

commit;
