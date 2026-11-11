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

Swagger/OpenAPI (solo se `API_DOCS_ENABLED` è attivo: di default sì in locale, no in produzione):
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`
- `http://localhost:8000/openapi.json`

Requisiti: Python 3.11-3.13 (il `Dockerfile` usa 3.12).

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
- `API_DOCS_ENABLED` (`true/false`, opzionale): pubblica `/docs`, `/redoc` e `/openapi.json`. Se non impostata vale `true`, tranne con `APP_ENV=prod` (o `production`), dove le docs interattive e lo schema OpenAPI non sono esposti (404). Il frontend non usa `/openapi.json`
- `JUSTETF_XRAY_AUTO_ENRICH_ENABLED` (`true/false`, opzionale): X-Ray (pagina, vista aggregata e Copilot) scarica da justETF e salva in cache i profili ETF mancanti. Se non impostata vale `true` solo con `APP_ENV=dev`. Via MCP X-Ray non scrive mai
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
- `auth.py`: verifica gli access token OAuth di Clerk (JWT `at+jwt` RS256 via JWKS, con refetch limitato, oppure opachi `oat_` via Backend API di Clerk, con cache positiva e negativa); rifiuta i session token della web app
- `tools.py`: costruisce i tool MCP dai soli tool di `TOOL_DEFINITIONS` (`app/copilot_tools.py`) elencati in `MCP_TOOL_ALLOWLIST` (più `list_portfolios`), valida gli argomenti, controlla che il `portfolio_id` appartenga all'utente e li esegue con `execute_tool` sotto timeout, limite di concorrenza e rate limit dei tool pesanti; ripulisce e limita l'output
- `routes.py`: endpoint ASGI `/mcp` (limite di autenticazioni fallite per IP, autenticazione, utenti ammessi/bloccati, rate limit per utente, solo POST, body max 1 MB, header `no-store`/`nosniff`, audit log) e documenti `/.well-known/oauth-protected-resource` e `/.well-known/oauth-authorization-server`

La registrazione avviene in `app/main.py` con `register_mcp_routes(...)`.

Variabili d'ambiente (elenco completo con default in `.env.example` e in `docs/mcp.md`):
- `MCP_ENABLED` (default `false`)
- `CLERK_AUTH_ENABLED=true` (obbligatoria: MCP non usa mai il fallback `dev-user`)
- `MCP_RESOURCE_URL` (URL pubblico dell'endpoint, in produzione `https://valore365.onrender.com/mcp`; `http` ammesso solo per localhost)
- `CLERK_ISSUER` (Frontend API URL di Clerk)
- `CLERK_SECRET_KEY` (solo se Clerk emette token opachi `oat_`)
- opzionali: `CLERK_API_URL`, `MCP_ALLOWED_CLIENT_IDS`, `MCP_SCOPES_SUPPORTED`, `MCP_REQUIRED_SCOPES`, `MCP_REQUIRE_AUDIENCE`, `MCP_ALLOWED_ORIGINS`, `MCP_RATE_LIMIT_REQUESTS`, `MCP_RATE_LIMIT_WINDOW_SECONDS`, `MCP_TOKEN_CACHE_SECONDS`
- hardening (vedi [`docs/mcp.md`](../../docs/mcp.md#hardening)): `MCP_AUTH_FAILURE_LIMIT`, `MCP_AUTH_FAILURE_WINDOW_SECONDS`, `MCP_NEGATIVE_TOKEN_CACHE_SECONDS`, `MCP_MAX_TOKEN_LIFETIME_SECONDS`, `MCP_TOOL_TIMEOUT_SECONDS`, `MCP_MAX_CONCURRENT_CALLS_PER_USER`, `MCP_HEAVY_TOOL_RATE_LIMIT_REQUESTS`, `MCP_HEAVY_TOOL_RATE_LIMIT_WINDOW_SECONDS`, `MCP_ALLOWED_USER_IDS`, `MCP_BLOCKED_USER_IDS` (più `TRUSTED_PROXY_IPS` per l'IP del client dietro proxy). Tutti i limiti sono in memoria, per processo

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

## Auditor dei calcoli

L'Auditor (`app/services/auditor/`) verifica i numeri esposti dai tool MCP con 52 regole
deterministiche (stress test, ribilanciamento e PAC, costi e reddito, coerenza fra tool). Catalogo:
[`docs/auditor/rules.md`](../../docs/auditor/rules.md); contratto e codici:
[`docs/auditor/architecture.md`](../../docs/auditor/architecture.md). Non scrive nel database e non
usa la rete (provider di mercato offline).

### Eseguirlo in locale

Serve un PostgreSQL con schema, migrazioni e il seed dei portafogli di prova
(`scripts/auditor/audit_seed.sql`, utente `auditor-seed-user`, portafogli 9101-9107). Meglio un
database dedicato, così il seed non si mescola con i dati di sviluppo. Con il `db` di docker compose,
da root repository:

```bash
docker compose up -d db
export PGURL=postgresql://postgres:postgres@localhost:5432/valore365_auditor
psql postgresql://postgres:postgres@localhost:5432/postgres -c "create database valore365_auditor"
psql "$PGURL" -v ON_ERROR_STOP=1 -f database/schema.sql
for f in $(ls database/migrations/*.sql | sort); do psql "$PGURL" -v ON_ERROR_STOP=1 -f "$f"; done
psql "$PGURL" -v ON_ERROR_STOP=1 -f scripts/auditor/audit_seed.sql
```

Il seed è riapplicabile (cancella e ricrea i propri dati) e ha date relative a oggi: riapplicalo se
il database ha qualche giorno. Poi, da `src/backend`, con `DATABASE_URL` puntato a quel database
(anche i tool del Doctor lo leggono da lì):

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/valore365_auditor
python -m app.services.auditor --user auditor-seed-user --mode ci --fail-on P1 \
    --json-out auditor-report.json --md-out auditor-report.md
```

Opzioni utili: `--rule B-PAC-SUM` e `--group A` (ripetibili) per restringere le regole,
`--portfolio 9101` per un solo portafoglio, `--no-aggregate` / `--no-instruments` per saltare la
vista aggregata o gli scope per strumento, `--strict-known` per far contare anche i difetti noti,
`--list-rules` per l'elenco (non serve il database). Codici di uscita: **0** nessun `fail`/`error`
alla soglia (`--fail-on`, default P1: contano P0 e P1), **1** almeno uno, **2** l'Auditor non è
partito (argomenti, database, utente senza portafogli, report non valido).

Lo stesso giro, senza database da preparare a mano, lo fa il test di integrazione
`tests/integration/test_auditor_postgres.py` (cluster Postgres 16 usa e getta, binari in
`/usr/lib/postgresql/16/bin` o `$PG_BIN`; saltato se mancano):

```bash
python -m pytest tests/integration/test_auditor_postgres.py tests/integration/test_auditor_seed_postgres.py -q
```

### In CI

`.github/workflows/auditor.yml` gira sulle PR che toccano `src/backend/**`, `database/**`,
`scripts/auditor/**` o il workflow, ogni notte e a mano (*Run workflow*). Avvia un `postgres:16`,
applica schema, migrazioni e seed, esegue il comando sopra e fallisce se il codice di uscita non è 0.
Il report Markdown è nel riepilogo del job (*Summary*), il JSON nell'artefatto `auditor-report`,
anche quando il job fallisce.

### Leggere il report

- **Titolo**: `superato` (codice di uscita 0) o `non superato`.
- **Tabella severità × esito**: conteggi di `pass`, `fail`, `skip`, `error` per P0 (numero sbagliato
  che porta a una decisione sbagliata), P1 (numeri incoerenti fra tool o incompleti presentati come
  completi), P2 (trasparenza, metadati). Sotto, il numero di `fail` su difetti noti.
- **Fallimenti ed errori**: per regola e per scope (`portfolio:9101`, `aggregate:9101,…`,
  `instrument:9104:AUDUS.L`, `user`), il motivo e le evidenze nella forma
  `campo` (tool): osservato → atteso, tolleranza. Gli argomenti esatti della chiamata sono nel JSON
  (`results[].evidence[].args`), così il caso si riproduce con lo stesso tool.
- **Regole saltate**: `skip` con il codice (`empty_portfolio`, `no_targets`, `not_applicable`,
  `no_reference_data`, …). Uno `skip` non è un esito negativo, ma sui portafogli della colonna
  «Prova» del catalogo non deve esserci: lo verifica il test di integrazione.
- **Esiti per scope** e **Chiamate ai tool** (totali, dalla memo, errori: i rifiuti attesi, come una
  vendita oltre il valore della posizione nel what-if, contano fra gli errori dei tool ma non sono
  `error` delle regole).
- `error` è del motore, non della regola: `exception`, `timeout`, `tool_error` (il tool ha risposto
  con un errore inatteso), `invalid_outcome`, `deadline_exceeded`.

### Quando una regola fallisce

1. Riproduci con `--rule <ID> --portfolio <id>` e leggi la scheda della regola in `rules.md`
   (condizione, tolleranze e il loro motivo in §0.2).
2. Stabilisci di chi è il difetto:
   - **codice applicativo** (il numero è davvero sbagliato o incoerente): è il caso per cui
     l'Auditor esiste. Correggi il codice nella stessa PR, oppure, se la correzione è un lavoro a sé,
     marcalo come difetto noto (sotto). Non si indebolisce mai una regola per farla passare;
   - **regola o seed** (tolleranza che non tiene conto di un arrotondamento che il tool fa davvero,
     precondizione sbagliata, dato del seed incoerente): correggi la regola o il seed con un test
     unitario che lo dimostri e una nota nella sottosezione del tuo task in «Deviazioni» di
     `architecture.md`;
   - **ambiente** (database non aggiornato, seed vecchio di giorni, migrazione mancante): di solito
     dà `error` o codice di uscita 2; riapplica schema, migrazioni e seed.

### Marcare un difetto noto

Quando una regola trova un difetto reale che non si corregge subito:

1. apri un task nel backlog (`backlog/tasks/task-NN - ….md`, milestone `m-1` se riguarda
   l'accuratezza dei calcoli) con descrizione, evidenza dal report (comando, scope, evidenze) e
   criteri di accettazione;
2. aggiungi `"known_defect": "TASK-NN"` alla dichiarazione della regola in
   `app/services/auditor/rules/*.py` (la regola resta attiva);
3. aggiungi la riga nella sezione «Difetti noti» di `docs/auditor/rules.md` (il test di
   integrazione verifica che dichiarazioni e sezione coincidano e che il task esista).

Un `fail` su una regola marcata compare nel report ma non fa fallire la CI (`--strict-known` lo
rende di nuovo bloccante); un `error` conta sempre. Quando il task è chiuso si tolgono il campo e la
riga. Oggi è marcata solo `B-PAC-SUM` (TASK-83).
