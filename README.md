  <img src="src/frontend/valore-frontend/src/assets/logo-mark.svg" alt="Logo Valore365" width="40">

# Valore365

SaaS di portfolio tracking personale (no execution) 📈

Include:
- 📂 gestione portfolio e transazioni
- 🎯 target allocation
- 💹 prezzi e storico (provider finanziario configurabile, default `yfinance`)
- 📊 dashboard con KPI, posizioni e analisi

## 🏗️ Architettura (stato attuale)
- `database/`: schema SQL, seed e migrazioni PostgreSQL
- `src/backend/`: API FastAPI + logica pricing/historical + scheduler opzionale
- `src/frontend/valore-frontend/`: SPA React + Vite + Mantine
- `scripts/`: script PowerShell di bootstrap DB e avvio backend

## ✨ Funzionalita principali
- 🗂️ CRUD portfolio (`target_notional`, `cash_balance`, valuta base, timezone)
- 🔁 CRUD transazioni (`buy/sell`, fee, tasse, note)
- 🔎 Ricerca asset (`DB + provider`) con `discover` e `ensure`
- 🎯 Target allocation e confronto con performance target
- 📈 Dashboard con KPI di portafoglio, posizioni, allocazione, time series 1Y e analisi target/intraday
- ♻️ Refresh prezzi e backfill storico giornaliero
- 🔐 Auth opzionale via Clerk (frontend + backend)

## 🗃️ Struttura repository
- `README.md`: panoramica progetto (questo file)
- `database/schema.sql`: schema base PostgreSQL
- `database/seed.sql`: seed iniziale
- `database/migrations/*.sql`: migrazioni incrementali
- `docker-compose.yml`: stack locale Docker (DB + API + frontend dev/prod profile)
- `docs/`: documentazione tecnica e note progetto
- `src/backend/README.md`: setup/uso backend
- `src/frontend/valore-frontend/README.md`: setup/uso frontend

## 🚀 Setup locale rapido (senza Docker)
1. Avvia PostgreSQL locale e crea DB `valore365`.
2. Applica schema/seed/migrazioni:
- PowerShell: `./scripts/bootstrap_db.ps1`
- oppure manualmente con `psql` (`database/schema.sql`, `database/seed.sql`, poi `database/migrations/*.sql`)
3. Crea `src/backend/.env` (manuale) con almeno:
- `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/valore365`
- `FINANCE_PROVIDER=yfinance`
- `CLERK_AUTH_ENABLED=false`
4. Avvia backend:
- PowerShell: `./scripts/run_backend.ps1`
- oppure da `src/backend`: `uvicorn app.main:app --reload --port 8000`
5. Avvia frontend:
- `cd src/frontend/valore-frontend`
- `npm install`
- `npm run dev`
6. Apri `http://localhost:5173` (frontend) e `http://localhost:8000/docs` (Swagger backend).

## 🐳 Docker Compose
Da root progetto:

- Dev completo (DB + API reload + frontend nginx su `:8080`):
```bash
docker compose --profile dev up --build
```

- Stack prod-like completo (DB + API + frontend):
```bash
docker compose --profile prod up --build
```

Note:
- Il servizio `frontend` è presente solo nel profilo `dev`.
- Il servizio `frontend-prod` è presente nel profilo `prod`.
- `frontend` usa proxy `/api -> api-dev:8000` e `frontend-prod` usa `/api -> api-prod:8000`.

## ☁️ Deploy (beta) consigliato
Per una beta SaaS, la combinazione più pragmatica con questo codice è:
- `Frontend`: Vercel (build statico Vite)
- `Database`: Supabase Postgres
- `Backend`: Render / Fly.io / Railway (FastAPI)

Importante:
- il frontend usa `/api` come base path hardcoded (`src/frontend/valore-frontend/src/services/api.ts`)
- in produzione serve un reverse proxy/rewrite verso il backend (oppure una modifica del client API per URL configurabile)

## 🧪 Test
- Backend unit/integration: vedi `src/backend/README.md`
- Smoke REST script: `scripts/e2e/rest_be_smoke.sh` (adatta URL/token al tuo ambiente)

## 🤖 Portfolio Copilot (AI chatbot)
Un assistente AI integrato nel dashboard che spiega in linguaggio semplice i dati del portafoglio (performance, allocazione, drift, cash, best/worst performer).

**Non** fornisce consulenza finanziaria, **non** esegue azioni sul DB.

### Attivazione
Aggiungi al `.env` del backend:

```bash
# Scegli un provider: "openai" | "anthropic" | "gemini" | "local"
COPILOT_PROVIDER=openai

# Inserisci la API key del provider scelto
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=AI...

# Modello (opzionale, lasciare vuoto per il default)
# Default: openai=gpt-4o-mini, anthropic=claude-sonnet-4-20250514, gemini=gemini-2.0-flash, local=llama3.2:3b
COPILOT_MODEL=
```

### LLM locale (sviluppo)
Per usare Ollama o LM Studio in locale senza costi API:

```bash
COPILOT_PROVIDER=local
COPILOT_MODEL=llama3.2:3b
COPILOT_LOCAL_URL=http://localhost:11434/v1
```

Prerequisito: avere Ollama installato e il modello scaricato (`ollama pull llama3.2:3b`).

### Disattivazione
Lasciare `COPILOT_PROVIDER=` vuoto (o rimuoverlo). Il bottone del copilot non apparira nel frontend.

### Documentazione
Piano completo di implementazione: [`docs/PORTFOLIO_COPILOT_PIANO_CLAUDE.md`](docs/PORTFOLIO_COPILOT_PIANO_CLAUDE.md)

## 🏁 Feature Flag Target Allocation (ripristino rapido)
La logica esclusivamente legata a Target Allocation puo essere disattivata/riattivata senza patchare il codice:

- Backend: `ENABLE_TARGET_ALLOCATION=false|true`
- Frontend: `VITE_ENABLE_TARGET_ALLOCATION=false|true`

Valori consigliati:
- `false`: disattiva API/UI target-only (allocazione target, performance target, rebalance target).
- `true`: ripristina tutte le funzionalita target.
