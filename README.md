# Valore365

Portfolio tracker personale con prezzi realtime e vista storica annuale.

## Scope V1
- Tracking portafoglio (no trading)
- Prezzi realtime + storico 1Y
- Calcoli in valuta base del portafoglio

## Struttura progetto
- `database/schema.sql`: schema SQL completo
- `database/seed.sql`: seed iniziale portfolio e asset
- `database/migrations/`: migrazioni incrementali
- `src/backend`: API FastAPI e logica business
- `src/frontend`: dashboard frontend
- `scripts`: script di bootstrap e run

## Backend stato attuale
- API anagrafiche asset (`POST /assets`, `POST /asset-provider-symbols`)
- Ingest realtime (`POST /prices/refresh`) con retry/backoff/rate-limit
- Backfill daily (`POST /prices/backfill-daily`) su prezzi + FX
- Timeseries 1Y reale (`transactions + price_bars_1d + fx_rates_1d`)
- Error model uniforme e idempotenza ingest
- Scheduler automatico prezzi opzionale

## Frontend stato attuale
- Bootstrap React + Vite + TypeScript in `src/frontend`
- Dashboard base con fetch da API backend (`summary`, `positions`, `timeseries`)
- Stile responsive iniziale e configurazione via `.env`
- Pronto per integrazione grafici (ECharts/Recharts) nei prossimi step

## Run rapido
1. Configurare `.env` in `src/backend`
2. Applicare schema/seed (o script `scripts/bootstrap_db.ps1`)
3. Avviare backend (`scripts/run_backend.ps1`)

## Docker
- Dev: `docker compose --profile dev up --build`
- Prod-like: `docker compose --profile prod up --build`
