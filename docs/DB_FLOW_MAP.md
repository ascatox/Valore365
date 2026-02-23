# Flusso DB + Twelve Data (API e Postgres)

Obiettivo: elencare tutte le chiamate che usano il DB e delineare il flusso combinato tra Twelve Data e Postgres.

## A) Endpoint REST che usano il DB

### Asset e mapping
- `POST /api/assets`
  - DB: `assets`
  - Scopo: crea asset locale.
- `POST /api/asset-provider-symbols`
  - DB: `asset_provider_symbols`
  - Scopo: mappa asset locale → simbolo provider.
- `GET /api/assets/{id}`
  - DB: `assets`
- `GET /api/assets/search?q=...`
  - DB: `assets`

### Transazioni
- `POST /api/transactions`
  - DB: `transactions`
- `GET /api/portfolios/{id}/positions`
  - DB: `transactions`, `assets`, `price_bars_1d` (prezzo daily), `fx_rates_1d` (se FX attivo)

### Portfolio
- `GET /api/portfolios/{id}/summary`
  - DB: aggrega da `positions` (quindi usa `transactions`, `price_bars_1d`, `fx_rates_1d`)
- `GET /api/portfolios/{id}/timeseries?range=1y&interval=1d`
  - DB: `transactions`, `price_bars_1d`, `fx_rates_1d`
- `GET /api/portfolios/{id}/allocation`
  - DB: `positions` (quindi usa `transactions`, `price_bars_1d`, `fx_rates_1d`)

### Prezzi (ingest + storico)
- `POST /api/prices/backfill-daily`
  - DB write: `price_bars_1d`, `fx_rates_1d`
  - DB read: `assets`, `asset_provider_symbols`, `portfolios`
- `POST /api/prices/refresh` (se mantenuto)
  - DB write: `price_ticks` (se usato) oppure `price_bars_1d` (se adattato a daily)
  - DB read: `assets`, `asset_provider_symbols`, `portfolios`

### Idempotenza (se usata)
- DB: `api_idempotency_keys`

## B) Flusso combinato Twelve Data → DB Postgres

### 1) Ricerca simboli
- FE: `GET /api/symbols?q=...`
- BE: chiama Twelve Data `symbol_search`
- DB: nessuna scrittura (solo lookup esterno)

### 2) Onboarding asset
- FE: `POST /api/assets`
- BE: salva `assets`
- FE: `POST /api/asset-provider-symbols`
- BE: salva `asset_provider_symbols`

### 3) Aggiornamento manuale prezzi daily
- FE: `POST /api/prices/backfill-daily?portfolio_id=...&days=...`
- BE:
  1. Legge `assets` e mapping provider.
  2. Chiama Twelve Data `time_series` (daily) per ogni asset.
  3. Salva su `price_bars_1d`.
  4. Determina valute non EUR e chiama `time_series` FX.
  5. Salva su `fx_rates_1d`.
  6. (Retention) elimina righe oltre 730 giorni.

### 4) Consultazione dati (solo DB)
- Dashboard/Portfolio leggono solo dal DB:
  - Positions, Summary, Allocation, Timeseries
- Nessuna chiamata Twelve Data in lettura.

## C) Tabelle DB coinvolte
- `portfolios`
- `assets`
- `asset_provider_symbols`
- `transactions`
- `price_bars_1d`
- `fx_rates_1d`
- `price_ticks` (solo se mantenuto)
- `api_idempotency_keys` (idempotenza ingest)

## D) Nota operativa
Tutte le API di Twelve Data devono essere invocate solo dal backend.
Il frontend deve consumare solo REST API locali.
