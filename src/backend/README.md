# Backend - Valore365

API FastAPI collegata a PostgreSQL.

## Endpoint disponibili
- `GET /health`
- `POST /assets`
- `GET /assets/{id}`
- `POST /asset-provider-symbols`
- `GET /assets/search?q=...`
- `POST /transactions`
- `POST /prices/refresh`
- `POST /prices/backfill-daily`
- `GET /portfolios/{id}/positions`
- `GET /portfolios/{id}/summary`
- `GET /portfolios/{id}/timeseries?range=1y&interval=1d`
- `GET /portfolios/{id}/allocation`

## Error Model
Le API restituiscono errori uniformi:
`{"error": {"code": "...", "message": "..."}}`

## Idempotenza ingest
Supportata su:
- `POST /prices/refresh`
- `POST /prices/backfill-daily`

Header:
- `Idempotency-Key: <chiave-univoca>`

## Prerequisiti DB
1. Creare database PostgreSQL (es. `valore365`)
2. Eseguire `database/schema.sql` e `database/seed.sql`
3. Per DB gia esistenti, applicare anche `database/migrations/20260217_01_operational_updates.sql`

## Configurazione backend
1. Copiare `src/backend/.env.example` in `src/backend/.env`
2. Impostare le variabili principali:
- `DATABASE_URL`
- `FINANCE_PROVIDER` (`twelvedata`)
- `FINANCE_API_KEY`
- `PRICE_SCHEDULER_ENABLED`
- `PRICE_SCHEDULER_INTERVAL_SECONDS`

Nota: `.env` e' ignorato da git.

## Scheduler prezzi
- Abilita con `PRICE_SCHEDULER_ENABLED=true`
- Intervallo con `PRICE_SCHEDULER_INTERVAL_SECONDS`
- Scope portfolio opzionale con `PRICE_SCHEDULER_PORTFOLIO_ID`

## Run locale
1. `python -m venv .venv`
2. `.venv\\Scripts\\Activate.ps1`
3. `pip install -r requirements.txt`
4. `uvicorn app.main:app --reload --port 8000`

## Docker (profili)
Da root progetto:
- Dev: `docker compose --profile dev up --build`
- Prod-like: `docker compose --profile prod up --build`

## Script utili
Da root progetto:
- Bootstrap DB: `./scripts/bootstrap_db.ps1`
- Run backend: `./scripts/run_backend.ps1`

## Test non-E2E
1. `pip install -r requirements-dev.txt`
2. `pytest tests`
