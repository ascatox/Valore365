# Backend - Valore365

API `FastAPI` per portfolio tracking, transazioni, target allocation e pricing/historical ingestion su PostgreSQL.

## Stack
- `FastAPI`
- `SQLAlchemy 2`
- `psycopg 3`
- `APScheduler` (refresh prezzi opzionale)
- `httpx`
- provider prezzi/ricerca simboli: default `yfinance`

## Avvio locale
Da `src/backend`:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# oppure .venv\Scripts\Activate.ps1 su Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Swagger/OpenAPI:
- `http://localhost:8000/docs`
- `http://localhost:8000/openapi.json`

Health:
- `GET /api/health`

## Configurazione (`src/backend/.env`)
Il backend legge un file `.env` in `src/backend/` (non esiste un `.env.example` nel repository al momento).

Variabili principali:
- `APP_ENV` (`dev`/`prod`, default `dev`)
- `DATABASE_URL` (default locale Postgres)
- `FINANCE_PROVIDER` (default `yfinance`)
- `FINANCE_API_BASE_URL` (opzionale)
- `FINANCE_API_KEY` (opzionale, dipende dal provider)
- `FINANCE_REQUEST_TIMEOUT_SECONDS`
- `FINANCE_MAX_RETRIES`
- `FINANCE_RETRY_BACKOFF_SECONDS`
- `FINANCE_SYMBOL_REQUEST_DELAY_SECONDS`
- `PRICE_SCHEDULER_ENABLED` (`true/false`)
- `PRICE_SCHEDULER_INTERVAL_SECONDS`
- `PRICE_SCHEDULER_PORTFOLIO_ID` (opzionale)
- `CLERK_AUTH_ENABLED` (`true/false`)
- `CLERK_JWKS_URL` (obbligatoria se Clerk abilitato)
- `CLERK_AUTHORIZED_PARTIES` (CSV opzionale)
- `CORS_ALLOWED_ORIGINS` (CSV, usata in `prod`)

Note:
- In `APP_ENV=dev` il backend abilita CORS permissivo (`*`).
- Con `CLERK_AUTH_ENABLED=false`, tutte le route API (tranne `/health`) passano con utente fittizio `dev-user`.

## Database
Prerequisito: PostgreSQL raggiungibile dal `DATABASE_URL`.

Da root repository puoi usare lo script PowerShell:
- `./scripts/bootstrap_db.ps1`

Lo script applica in ordine:
- `database/schema.sql`
- `database/seed.sql`
- tutte le migrazioni in `database/migrations/*.sql` (ordinate per nome)

In alternativa puoi usare `psql` manualmente.

## Endpoint API (principali)
Tutte le route applicative sono prefissate da `/api`.

Portfolio:
- `POST /api/portfolios`
- `GET /api/admin/portfolios`
- `PATCH /api/portfolios/{portfolio_id}`
- `DELETE /api/portfolios/{portfolio_id}`

Asset:
- `POST /api/assets`
- `GET /api/assets/search?q=...`
- `GET /api/assets/discover?q=...` (DB + provider)
- `POST /api/assets/ensure`
- `GET /api/assets/{asset_id}`
- `GET /api/assets/{asset_id}/latest-quote`
- `POST /api/asset-provider-symbols`
- `GET /api/symbols?q=...`

Transazioni:
- `GET /api/portfolios/{portfolio_id}/transactions`
- `POST /api/transactions`
- `PATCH /api/transactions/{transaction_id}`
- `DELETE /api/transactions/{transaction_id}`

Pricing / storico:
- `POST /api/prices/refresh`
- `POST /api/prices/backfill-daily`

Analytics / dashboard:
- `GET /api/portfolios/{portfolio_id}/summary`
- `GET /api/portfolios/{portfolio_id}/positions`
- `GET /api/portfolios/{portfolio_id}/allocation`
- `GET /api/portfolios/{portfolio_id}/timeseries?range=1y&interval=1d`
- `GET /api/portfolios/{portfolio_id}/target-allocation`
- `POST /api/portfolios/{portfolio_id}/target-allocation`
- `DELETE /api/portfolios/{portfolio_id}/target-allocation/{asset_id}`
- `GET /api/portfolios/{portfolio_id}/target-performance`
- `GET /api/portfolios/{portfolio_id}/target-performance/intraday?date=YYYY-MM-DD`
- `GET /api/portfolios/{portfolio_id}/target-performance/assets`
- `GET /api/portfolios/{portfolio_id}/target-performance/assets/intraday?date=YYYY-MM-DD`

## Error model
Errori applicativi uniformi:

```json
{
  "error": {
    "code": "bad_request",
    "message": "..."
  }
}
```

Le validation errors FastAPI sono adattate allo stesso shape (`422`).

## Idempotenza ingest
Supportata su:
- `POST /api/prices/refresh`
- `POST /api/prices/backfill-daily`

Header supportato:
- `Idempotency-Key: <chiave-univoca>`

## Scheduler prezzi
Lo scheduler viene avviato nel `lifespan` FastAPI.

Configurazione:
- `PRICE_SCHEDULER_ENABLED=true`
- `PRICE_SCHEDULER_INTERVAL_SECONDS=60` (esempio)
- `PRICE_SCHEDULER_PORTFOLIO_ID=...` (opzionale, limita lo scope)

## Auth (Clerk opzionale)
Backend:
- abilita con `CLERK_AUTH_ENABLED=true`
- imposta `CLERK_JWKS_URL`
- opzionale `CLERK_AUTHORIZED_PARTIES` (CSV)

Comportamento:
- tutte le route API (tranne `/api/health`) richiedono `Authorization: Bearer <token>` quando auth è attiva
- con auth disattiva, il backend accetta richieste senza token

## Docker
Da root repository:

- Dev (con `api-dev` + DB + frontend separato nel profilo `dev`):
```bash
docker compose --profile dev up --build
```

- Prod-like backend+DB:
```bash
docker compose --profile prod up --build
```

## Test
Da `src/backend`:

```bash
pip install -r requirements-dev.txt
pytest tests
```

Suite presenti:
- `tests/unit`
- `tests/integration`

Se i test integration dipendono da DB/provider, prepara variabili e database coerenti con l'ambiente locale.
