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
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Swagger/OpenAPI:
- `http://localhost:8000/docs`
- `http://localhost:8000/openapi.json`

Health:
- `GET /api/health`

## Configurazione (`src/backend/.env`)
Il backend legge un file `.env` in `src/backend/`. Puoi partire da `src/backend/.env.example`.

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
- `MCP_ENABLED`, `MCP_RESOURCE_URL`, `CLERK_ISSUER`, ... (server MCP, vedi [Server MCP](#server-mcp-sola-lettura))

Note:
- In `APP_ENV=dev` il backend abilita CORS permissivo (`*`).
- Con `CLERK_AUTH_ENABLED=false`, tutte le route API (tranne `/health`) passano con utente fittizio `dev-user`.
- Il fallback `dev-user` non vale per `/mcp`: senza Clerk il server MCP non viene servito.

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
- `POST /api/public/portfolio/analyze`
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

## Server MCP (sola lettura)
Il backend espone un server [MCP](https://modelcontextprotocol.io) remoto su `POST /mcp` (fuori dal prefisso `/api`), che permette a Claude, ChatGPT e altri client MCP di **leggere** i portafogli dell'utente autenticato con OAuth Clerk. Documentazione tecnica completa: [`docs/mcp.md`](../../docs/mcp.md); guida per gli utenti finali: [`docs/mcp-guida-utente.md`](../../docs/mcp-guida-utente.md).

Struttura del modulo `app/mcp_server/`:
- `config.py`: valida le impostazioni e ricava gli URL pubblicati; se qualcosa manca l'endpoint non viene servito (*fail closed*)
- `auth.py`: verifica gli access token OAuth di Clerk (JWT `at+jwt` via JWKS oppure opachi `oat_` via Backend API di Clerk); rifiuta i session token della web app
- `tools.py`: costruisce i tool MCP a partire da `TOOL_DEFINITIONS` di `app/copilot_tools.py` (più `list_portfolios`), controlla che il `portfolio_id` appartenga all'utente e li esegue con `execute_tool`
- `routes.py`: endpoint ASGI `/mcp` (autenticazione, rate limit per utente, solo POST, body max 1 MB) e documenti `/.well-known/oauth-protected-resource` e `/.well-known/oauth-authorization-server`

La registrazione avviene in `app/main.py` con `register_mcp_routes(...)`.

Variabili d'ambiente (elenco completo con default in `.env.example` e in `docs/mcp.md`):
- `MCP_ENABLED` (default `false`)
- `CLERK_AUTH_ENABLED=true` (obbligatoria: MCP non usa mai il fallback `dev-user`)
- `MCP_RESOURCE_URL` (URL pubblico dell'endpoint, es. `https://<host-backend>/mcp`; `http` ammesso solo per localhost)
- `CLERK_ISSUER` (Frontend API URL di Clerk)
- `CLERK_SECRET_KEY` (solo se Clerk emette token opachi `oat_`)
- opzionali: `CLERK_API_URL`, `MCP_ALLOWED_CLIENT_IDS`, `MCP_SCOPES_SUPPORTED`, `MCP_REQUIRED_SCOPES`, `MCP_REQUIRE_AUDIENCE`, `MCP_ALLOWED_ORIGINS`, `MCP_RATE_LIMIT_REQUESTS`, `MCP_RATE_LIMIT_WINDOW_SECONDS`, `MCP_TOKEN_CACHE_SECONDS`

Comportamento:
- `MCP_ENABLED=false` → `/mcp` risponde `404`; abilitato ma configurazione incompleta → `503` con l'errore nei log
- senza token o con token non valido → `401` con `WWW-Authenticate: Bearer resource_metadata="..."`

Test:

```bash
pytest tests/integration/test_mcp_server.py
```

I test usano JWT firmati con chiavi generate al volo e un repository finto: non servono Clerk né il database.

Prova in locale (serve un'istanza Clerk di sviluppo con le OAuth applications e la Dynamic Client Registration attive):

```bash
# in .env: CLERK_AUTH_ENABLED=true, CLERK_JWKS_URL, CLERK_ISSUER,
#          MCP_ENABLED=true, MCP_RESOURCE_URL=http://localhost:8000/mcp
uvicorn app.main:app --reload --port 8000

# 401 atteso, con l'header WWW-Authenticate
curl -i -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'

# test completo con login OAuth (trasporto Streamable HTTP, URL http://localhost:8000/mcp);
# aggiungere http://localhost:6274 a MCP_ALLOWED_ORIGINS per la durata del test
npx @modelcontextprotocol/inspector
```

Dettagli (Inspector, curl con token, Claude Code in locale): [`docs/mcp.md`](../../docs/mcp.md#sviluppo-e-test-in-locale).

## Docker
Da root repository:

- Dev (con `api-dev` + DB + frontend separato nel profilo `dev`):
```bash
docker compose --profile dev up --build
```

- Prod-like completo (backend + DB + frontend-prod):
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
