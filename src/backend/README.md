# Backend - Valore365

API FastAPI collegata a PostgreSQL.

## Endpoint disponibili
- `GET /api/health`
- `POST /api/portfolios`
- `GET /api/admin/portfolios`
- `POST /api/assets`
- `GET /api/assets/{id}`
- `POST /api/asset-provider-symbols`
- `GET /api/assets/search?q=...`
- `POST /api/transactions`
- `POST /api/prices/refresh`
- `POST /api/prices/backfill-daily`
- `GET /api/portfolios/{id}/positions`
- `GET /api/portfolios/{id}/summary`
- `GET /api/portfolios/{id}/timeseries?range=1y&interval=1d`
- `GET /api/portfolios/{id}/allocation`

## Swagger
- `GET /api/swagger`
- OpenAPI JSON: `GET /api/openapi.json`

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
- `CLERK_AUTH_ENABLED`
- `CLERK_JWKS_URL`
- `CLERK_AUTHORIZED_PARTIES` (opzionale, lista CSV)

Nota: `.env` e' ignorato da git.

## Scheduler prezzi
- Abilita con `PRICE_SCHEDULER_ENABLED=true`
- Intervallo con `PRICE_SCHEDULER_INTERVAL_SECONDS`
- Scope portfolio opzionale con `PRICE_SCHEDULER_PORTFOLIO_ID`

## Auth (Clerk - soluzione veloce)
- Abilita validazione token BE con `CLERK_AUTH_ENABLED=true`
- Imposta `CLERK_JWKS_URL` con endpoint JWKS del tenant Clerk
- Le route API (tranne `/health`) richiedono `Authorization: Bearer <token>`
- In sviluppo rapido puoi lasciare `CLERK_AUTH_ENABLED=false`

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
