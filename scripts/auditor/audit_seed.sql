-- Auditor dei calcoli (TASK-78) — portafogli di prova.
-- Contratto: docs/auditor/rules.md §1 (id, simboli, composizione, regole esercitate),
-- docs/auditor/architecture.md §6 e §9 (CI su Postgres effimero, determinismo, nessuna rete).
-- Valori risultanti documentati in scripts/auditor/README.md e verificati da
-- src/backend/tests/integration/test_auditor_seed_postgres.py.
--
-- Si applica DOPO database/schema.sql e tutte le migrazioni di database/migrations.
-- Utente: auditor-seed-user. Portafogli 9101-9107 (EUR), strumenti 9101-9113 (prefisso AUD).
-- Date relative a current_date, prezzi e cambi generati con formule deterministiche
-- (generate_series): lo stesso giorno di calendario produce sempre gli stessi numeri e i
-- valori "di oggi" (prezzi, cambi, quantità, liquidità) non dipendono dalla data.
-- TER, schede justETF e metadati yFinance sono nel seed: nessuna chiamata a Yahoo o justETF.
--
-- Riapplicabile: cancella prima le righe del seed (id 9101-9113, utente auditor-seed-user).
-- Le sequenze non vengono toccate (id espliciti ≥ 9101, nessuna collisione con
-- scripts/e2e/doctor2_seed.sql).

begin;

-- ---------------------------------------------------------------------------
-- Pulizia (riapplicazione)
-- ---------------------------------------------------------------------------
delete from portfolios where id between 9101 and 9107 or owner_user_id = 'auditor-seed-user';
delete from assets where id between 9101 and 9113;
delete from fx_rates_1d
 where provider = 'auditor-seed' and to_ccy = 'EUR' and from_ccy in ('USD', 'GBP');

-- ---------------------------------------------------------------------------
-- Portafogli (cash_balance = saldo di apertura: 0 ovunque, la liquidità nasce dai depositi)
-- ---------------------------------------------------------------------------
insert into portfolios (id, name, base_currency, owner_user_id, cash_balance) values
  (9101, 'AUD Bilanciato storico',  'EUR', 'auditor-seed-user', 0),
  (9102, 'AUD Solo obbligazioni',   'EUR', 'auditor-seed-user', 0),
  (9103, 'AUD Oro e materie prime', 'EUR', 'auditor-seed-user', 0),
  (9104, 'AUD Londra e valute',     'EUR', 'auditor-seed-user', 0),
  (9105, 'AUD Import',              'EUR', 'auditor-seed-user', 0),
  (9106, 'AUD Vuoto',               'EUR', 'auditor-seed-user', 0),
  (9107, 'AUD Quotazioni ferme',    'EUR', 'auditor-seed-user', 0);

-- ---------------------------------------------------------------------------
-- Strumenti (rules.md §1). ISIN fittizi: nessuna tabella di simboli/ISIN noti del
-- classificatore li riconosce, la classe dipende solo dai dati del seed.
-- ---------------------------------------------------------------------------
insert into assets (id, symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin) values
  (9101, 'AUDEQ.MI',   'AUD Global Equity UCITS ETF (Acc)',                         'etf',   'MIL',   'Borsa Italiana',         'EUR', 'IE00AUD09101'),
  (9102, 'AUDBD.MI',   'AUD Global Aggregate Bond UCITS ETF EUR Hedged (Acc)',      'etf',   'MIL',   'Borsa Italiana',         'EUR', 'IE00AUD09102'),
  (9103, 'AUDTECH.DE', 'AUD Nasdaq-100 Technology UCITS ETF (Dist)',                'etf',   'XETRA', 'Xetra',                  'EUR', 'IE00AUD09103'),
  (9104, 'AUDGOV.MI',  'AUD Euro Government Bond UCITS ETF (Dist)',                 'etf',   'MIL',   'Borsa Italiana',         'EUR', 'IE00AUD09104'),
  (9105, 'AUDHY.DE',   'AUD Euro High Yield Corporate Bond UCITS ETF (Dist)',       'stock', 'XETRA', 'Xetra',                  'EUR', 'IE00AUD09105'),
  (9106, 'AUDBTP',     'BTP Italia 2030 1,6%',                                      'bond',  'MOT',   'Borsa Italiana MOT',     'EUR', 'IT00AUD09106'),
  (9107, 'AUDGLD.DE',  'AUD Physical Gold ETC',                                     'stock', 'XETRA', 'Xetra',                  'EUR', 'DE00AUD09107'),
  (9108, 'AUDCMD.MI',  'AUD Broad Commodity Swap UCITS ETF',                        'etf',   'MIL',   'Borsa Italiana',         'EUR', 'IE00AUD09108'),
  (9109, 'AUDTHM.DE',  'AUD Thematic Frontier Opportunities UCITS ETF',             'etf',   'XETRA', 'Xetra',                  'EUR', 'LU00AUD09109'),
  (9110, 'AUDUS.L',    'AUD World Equity UCITS ETF USD (Acc)',                      'etf',   'LSE',   'London Stock Exchange',  'USD', 'IE00AUD09110'),
  (9111, 'AUDUK.L',    'AUD UK Gilts UCITS ETF GBP (Dist)',                         'etf',   'LSE',   'London Stock Exchange',  'GBP', 'IE00AUD09111'),
  (9112, 'AUDSTL.MI',  'AUD Europe Equity UCITS ETF (Acc)',                         'etf',   'MIL',   'Borsa Italiana',         'EUR', 'IE00AUD09112'),
  (9113, 'AUDNPC.MI',  'AUD Emerging Markets Equity UCITS ETF (Acc)',               'etf',   'MIL',   'Borsa Italiana',         'EUR', 'IE00AUD09113');

-- Simbolo del provider = simbolo salvato: il suffisso (.MI, .DE, .L) dà la borsa per il
-- controllo delle quotazioni ferme (sedute, TASK-53).
insert into asset_provider_symbols (asset_id, provider, provider_symbol)
select id, 'yfinance', symbol from assets where id between 9101 and 9113;

-- ---------------------------------------------------------------------------
-- Schede justETF (etf_enrichment; ter in punti percentuali) e metadati yFinance
-- (asset_metadata; dividend_yield in %, expense_ratio come frazione come lo salva yFinance).
-- AUDHY.DE, AUDBTP e AUDTHM.DE senza scheda; AUDTHM.DE anche senza metadati.
-- ---------------------------------------------------------------------------
insert into etf_enrichment (asset_id, isin, name, index_tracked, investment_focus, ter, country_weights, distribution_policy, source, fetched_at) values
  (9101, 'IE00AUD09101', 'AUD Global Equity UCITS ETF (Acc)', 'AUD Global Equity Index', 'Equity, World', 0.22,
   '[{"name":"United States","percentage":62.0},{"name":"Japan","percentage":5.5},{"name":"United Kingdom","percentage":3.5},{"name":"Other","percentage":29.0}]'::jsonb,
   'Accumulating', 'justetf', now()),
  (9102, 'IE00AUD09102', 'AUD Global Aggregate Bond UCITS ETF EUR Hedged (Acc)', 'AUD Global Aggregate Bond Index (EUR Hedged)', 'Bonds, World, Aggregate', 0.10,
   null, 'Accumulating', 'justetf', now()),
  (9103, 'IE00AUD09103', 'AUD Nasdaq-100 Technology UCITS ETF (Dist)', 'AUD Nasdaq-100 Technology Index', 'Equity, United States, Technology', 0.30,
   null, 'Distributing', 'justetf', now()),
  (9104, 'IE00AUD09104', 'AUD Euro Government Bond UCITS ETF (Dist)', 'AUD Euro Government Bond Index', 'Bonds, Euro, Government', 0.15,
   null, 'Distributing', 'justetf', now()),
  (9107, 'DE00AUD09107', 'AUD Physical Gold ETC', 'Gold', 'Precious Metals, Gold', 0.25,
   null, 'Accumulating', 'justetf', now()),
  (9108, 'IE00AUD09108', 'AUD Broad Commodity Swap UCITS ETF', 'AUD Broad Commodity Index', 'Commodities, Broad market', 0.19,
   null, 'Accumulating', 'justetf', now()),
  (9110, 'IE00AUD09110', 'AUD World Equity UCITS ETF USD (Acc)', 'AUD World Equity Index', 'Equity, World', 0.20,
   null, 'Accumulating', 'justetf', now()),
  (9111, 'IE00AUD09111', 'AUD UK Gilts UCITS ETF GBP (Dist)', 'AUD UK Gilts Index', 'Bonds, United Kingdom, Government', 0.07,
   null, 'Distributing', 'justetf', now()),
  (9112, 'IE00AUD09112', 'AUD Europe Equity UCITS ETF (Acc)', 'AUD Europe Equity Index', 'Equity, Europe', 0.12,
   null, 'Accumulating', 'justetf', now()),
  (9113, 'IE00AUD09113', 'AUD Emerging Markets Equity UCITS ETF (Acc)', 'AUD Emerging Markets Equity Index', 'Equity, Emerging Markets', 0.18,
   null, 'Accumulating', 'justetf', now());

insert into asset_metadata (asset_id, expense_ratio, category, dividend_yield, updated_at) values
  (9103, null,  null,              0.6, now()),
  (9104, null,  null,              2.5, now()),
  (9105, 0.005, 'High Yield Bond', 5.0, now()),   -- frazione: normalize_expense_ratio_pct → 0,5%
  (9106, null,  null,              1.6, now()),
  (9111, null,  null,              3.0, now());

-- ---------------------------------------------------------------------------
-- Prezzi giornalieri recenti (price_bars_1d), n = giorni prima di oggi.
-- close(n) = base × (1 − drift × (n − n0)) × (1 + amp × (sin((n − n0)/9 + phase) − sin(phase)))
-- dove n0 è la barra più recente: close(n0) = base esatto (valori di oggi tondi), la barra
-- precedente è diversa (variazione giornaliera non nulla).
--   9101 AUDEQ, AUDBD, AUDTECH: 0…400 (≥ 20 rendimenti nell'ultimo anno, Monte Carlo)
--   9104 AUDUS (USD), AUDUK (GBP): 0…400 (periodo delle transazioni coperto)
--   9102/9103 AUDGOV, AUDHY, AUDBTP, AUDGLD, AUDCMD, AUDTHM: solo 0…30 (nessuna finestra storica)
--   9107 AUDSTL: 30…60 (ultima barra 30 giorni fa: quotazione ferma)
--   9107 AUDNPC: solo oggi (nessuna chiusura precedente, nessun tick)
-- ---------------------------------------------------------------------------
with params(asset_id, base, phase, amp, drift, n0, n1) as (
  values
    (9101, 100.00::numeric, 0.3, 0.030, 0.00030, 0,  400),
    (9102,  50.00,          1.1, 0.008, 0.00005, 0,  400),
    (9103, 200.00,          2.0, 0.050, 0.00050, 0,  400),
    (9104, 120.00,          0.7, 0.006, 0.00004, 0,   30),
    (9105,  95.00,          1.9, 0.010, 0.00010, 0,   30),
    (9106, 101.00,          2.6, 0.004, 0.00002, 0,   30),
    (9107,  40.00,          0.5, 0.020, 0.00020, 0,   30),
    (9108,  20.00,          1.4, 0.025, 0.00015, 0,   30),
    (9109,  30.00,          2.3, 0.030, 0.00025, 0,   30),
    (9110, 110.00,          0.9, 0.025, 0.00030, 0,  400),
    (9111,  10.00,          1.7, 0.010, 0.00005, 0,  400),
    (9112,  60.00,          0.4, 0.020, 0.00010, 30,  60),
    (9113,  25.00,          0.0, 0.000, 0.00000, 0,    0)
),
series as (
  select p.asset_id, g.n,
         round(p.base * (1 - p.drift * (g.n - p.n0))::numeric
               * (1 + p.amp * (sin((g.n - p.n0) / 9.0 + p.phase) - sin(p.phase)))::numeric, 4) as close
  from params p
  cross join lateral generate_series(p.n0, p.n1) as g(n)
)
insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close, adj_close, volume)
select asset_id, 'yfinance', current_date - n,
       round(close * (1 + 0.002 * cos(n)::numeric), 4),
       round(close * 1.006, 4),
       round(close * 0.994, 4),
       close, close, 10000
from series;

-- ---------------------------------------------------------------------------
-- Storico per gli stress test storici (solo gli strumenti di 9101). Barre settimanali più
-- l'ultimo giorno di ogni finestra di HISTORICAL_SCENARIOS, prezzo lineare da p_start a
-- p_end: rendimento della finestra = p_end / p_start − 1 (diverso per strumento e scenario).
-- 9101 ha copertura 100% del valore investito → metodo "historical"; 9102 non ha barre
-- nelle finestre → "proxy". AUDEQ.MI e AUDBD.MI sono anche in 9103/9104/9105/9107.
-- ---------------------------------------------------------------------------
with windows(asset_id, d_start, d_end, p_start, p_end) as (
  values
    -- Dot-Com Crash 2000-03-01 … 2002-10-31
    (9101, date '2000-03-01', date '2002-10-31', 60.00::numeric, 36.00::numeric),   -- −40%
    (9102, date '2000-03-01', date '2002-10-31', 40.00, 44.80),                       -- +12%
    (9103, date '2000-03-01', date '2002-10-31', 80.00, 24.00),                       -- −70%
    -- Global Financial Crisis 2007-10-01 … 2009-03-31
    (9101, date '2007-10-01', date '2009-03-31', 70.00, 38.50),                       -- −45%
    (9102, date '2007-10-01', date '2009-03-31', 42.00, 43.68),                       -- +4%
    (9103, date '2007-10-01', date '2009-03-31', 60.00, 30.00),                       -- −50%
    -- Covid Crash 2020-02-19 … 2020-03-23
    (9101, date '2020-02-19', date '2020-03-23', 90.00, 63.00),                       -- −30%
    (9102, date '2020-02-19', date '2020-03-23', 52.00, 50.96),                       -- −2%
    (9103, date '2020-02-19', date '2020-03-23', 150.00, 112.50),                     -- −25%
    -- Bear Market 2022 2022-01-03 … 2022-10-12
    (9101, date '2022-01-03', date '2022-10-12', 95.00, 76.00),                       -- −20%
    (9102, date '2022-01-03', date '2022-10-12', 55.00, 46.75),                       -- −15%
    (9103, date '2022-01-03', date '2022-10-12', 210.00, 147.00)                      -- −30%
),
days as (
  select w.asset_id, w.d_start, w.d_end, w.p_start, w.p_end, g.d::date as d
  from windows w
  cross join lateral generate_series(w.d_start::timestamp, w.d_end::timestamp, interval '7 days') as g(d)
  union
  select w.asset_id, w.d_start, w.d_end, w.p_start, w.p_end, w.d_end
  from windows w
),
priced as (
  select asset_id, d,
         round(p_start + (p_end - p_start) * (d - d_start)::numeric / (d_end - d_start)::numeric, 4) as close
  from days
)
insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close, adj_close, volume)
select asset_id, 'yfinance', d, close, round(close * 1.01, 4), round(close * 0.99, 4), close, close, 10000
from priced;

-- ---------------------------------------------------------------------------
-- Cambi giornalieri (fx_rates_1d: rate = EUR per 1 unità di from_ccy), 0…400 giorni.
-- Oggi: USD 0,92, GBP 1,17 esatti.
-- ---------------------------------------------------------------------------
insert into fx_rates_1d (from_ccy, to_ccy, price_date, rate, provider)
select 'USD', 'EUR', current_date - n,
       round((0.92 * (1 + 0.010 * (sin(n / 15.0 + 0.2) - sin(0.2))))::numeric, 6), 'auditor-seed'
from generate_series(0, 400) as g(n)
union all
select 'GBP', 'EUR', current_date - n,
       round((1.17 * (1 + 0.008 * (sin(n / 20.0 + 0.5) - sin(0.5))))::numeric, 6), 'auditor-seed'
from generate_series(0, 400) as g(n);

-- ---------------------------------------------------------------------------
-- Transazioni. Ora 12:00 (stessa data in UTC e in Europe/Rome).
-- Dividendi: quantity 1 × price = importo lordo, nella valuta della transazione.
-- ---------------------------------------------------------------------------
insert into transactions (portfolio_id, asset_id, side, trade_at, quantity, price, fees, taxes, trade_currency, notes, owner_user_id)
select portfolio_id, asset_id, side, (current_date - days_ago) + time '12:00', quantity, price, fees, taxes, ccy, notes, 'auditor-seed-user'
from (values
  -- 9101 Bilanciato storico: deposito, acquisti e vendita negli ultimi 365 giorni
  -- (C1-TWR-MIXED), due dividendi EUR su AUDTECH.DE. Finale: 700 AUDEQ, 400 AUDBD, 50 AUDTECH.
  (9101, null::bigint, 'deposit',  300, 1::numeric,   100000.00::numeric, 0::numeric, 0::numeric, 'EUR', null::text),
  (9101, 9101,         'buy',      290, 750,           90.00,              1.50,       0,          'EUR', null),
  (9101, 9102,         'buy',      285, 400,           48.00,              1.50,       0,          'EUR', null),
  (9101, 9103,         'buy',      280, 50,            180.00,             1.50,       0,          'EUR', null),
  (9101, 9103,         'dividend', 200, 1,             30.00,              0,          0,          'EUR', null),
  (9101, 9101,         'sell',      60, 50,            98.00,              1.50,       0,          'EUR', null),
  (9101, 9103,         'dividend',  20, 1,             32.50,              0,          0,          'EUR', null),
  -- 9102 Solo obbligazioni (nessun target).
  (9102, null,         'deposit',   25, 1,             50000.00,           0,          0,          'EUR', null),
  (9102, 9104,         'buy',       24, 150,           118.00,             2.00,       0,          'EUR', null),
  (9102, 9105,         'buy',       24, 150,           94.00,              2.00,       0,          'EUR', null),
  (9102, 9106,         'buy',       24, 100,           100.50,             2.00,       0,          'EUR', null),
  -- 9103 Oro e materie prime.
  (9103, null,         'deposit',   28, 1,             42000.00,           0,          0,          'EUR', null),
  (9103, 9107,         'buy',       27, 400,           39.00,              2.00,       0,          'EUR', null),
  (9103, 9108,         'buy',       27, 400,           19.50,              2.00,       0,          'EUR', null),
  (9103, 9109,         'buy',       27, 200,           31.00,              2.00,       0,          'EUR', null),
  (9103, 9101,         'buy',       27, 100,           99.00,              2.00,       0,          'EUR', null),
  -- 9104 Londra e valute: acquisti in USD e GBP, dividendi GBP e EUR.
  (9104, null,         'deposit',  200, 1,             30000.00,           0,          0,          'EUR', null),
  (9104, 9110,         'buy',      190, 100,           105.00,             1.00,       0,          'USD', null),
  (9104, 9111,         'buy',      180, 800,           9.80,               1.00,       0,          'GBP', null),
  (9104, 9101,         'buy',      170, 80,            95.00,              1.00,       0,          'EUR', null),
  (9104, 9111,         'dividend',  90, 1,             40.00,              0,          0,          'GBP', null),
  (9104, 9101,         'dividend',  60, 1,             15.00,              0,          0,          'EUR', null),
  (9104, 9111,         'dividend',  10, 1,             42.00,              0,          0,          'GBP', null),
  -- 9105 Import: lotto CSV confermato; coppia legittima di acquisti identici (esecuzione
  -- frazionata) e dividendi mensili EUR di pari importo su date diverse.
  (9105, null,         'deposit',  150, 1,             20000.00,           0,          0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9101,         'buy',      140, 50,            96.00,              1.00,       0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9101,         'buy',      140, 50,            96.00,              1.00,       0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9102,         'buy',      140, 100,           49.00,              1.00,       0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9101,         'dividend', 120, 1,             12.00,              0,          0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9101,         'dividend',  90, 1,             12.00,              0,          0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9101,         'dividend',  60, 1,             12.00,              0,          0,          'EUR', 'Import CSV auditor-seed'),
  (9105, 9101,         'dividend',  30, 1,             12.00,              0,          0,          'EUR', 'Import CSV auditor-seed'),
  -- 9106 Vuoto: nessuna transazione.
  -- 9107 Quotazioni ferme.
  (9107, null,         'deposit',   60, 1,             20000.00,           0,          0,          'EUR', null),
  (9107, 9112,         'buy',       55, 100,           61.00,              1.00,       0,          'EUR', null),
  (9107, 9101,         'buy',       50, 50,            99.00,              1.00,       0,          'EUR', null),
  (9107, 9113,         'buy',        5, 200,           24.50,              1.00,       0,          'EUR', null)
) as t(portfolio_id, asset_id, side, days_ago, quantity, price, fees, taxes, ccy, notes);

-- Lotto d'import confermato di 9105 (il seed non passa dall'import CSV: la tabella
-- transactions non registra il lotto, il duplicato vero si riproduce nei test unitari).
insert into csv_import_batches (portfolio_id, owner_user_id, status, original_filename, source_sha256,
                                total_rows, valid_rows, error_rows, preview_data, created_at, committed_at)
values (9105, 'auditor-seed-user', 'committed', 'auditor-seed-import.csv',
        'a0d17005eed0000000000000000000000000000000000000000000000000009105',
        8, 8, 0, '[]'::jsonb, (current_date - 150) + time '11:00', (current_date - 150) + time '11:05');

-- Ultima sincronizzazione dei prezzi riuscita (data_freshness "ok"; nessuna rete coinvolta).
insert into market_data_sync_runs (trigger, status, started_at, finished_at, assets_requested, assets_updated)
values ('scheduler', 'success', now() - interval '20 minutes', now() - interval '19 minutes', 13, 12);

-- ---------------------------------------------------------------------------
-- Target di 9101: AUDEQ 50, AUDBD 40, AUDTECH 10 (oggi 70/20/10: le vendite di AUDEQ.MI
-- finanziano gli acquisti di AUDBD.MI). Nessun altro portafoglio ha target.
-- ---------------------------------------------------------------------------
insert into portfolio_target_allocations (portfolio_id, asset_id, weight_pct, owner_user_id) values
  (9101, 9101, 50, 'auditor-seed-user'),
  (9101, 9102, 40, 'auditor-seed-user'),
  (9101, 9103, 10, 'auditor-seed-user');

commit;
