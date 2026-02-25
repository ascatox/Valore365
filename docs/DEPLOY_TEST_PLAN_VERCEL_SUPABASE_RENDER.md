# Piano Ambiente di Test - Vercel + Supabase + Backend FastAPI

## Obiettivo
Portare `Valore365` in un ambiente di test cloud stabile per validare:
- onboarding/login (Clerk)
- CRUD portfolio/transazioni
- pricing/backfill
- dashboard
- stabilita base (errori, timeout, CORS, auth)

Stack consigliato:
- `Frontend`: Vercel
- `Database`: Supabase Postgres
- `Backend API`: Render (FastAPI)

Nota: il punto piu importante da decidere e gestire e il backend Python (non Vercel/Supabase).

## Perche questa combinazione
- `Vercel` e ottimo per frontend React/Vite e preview deploy.
- `Supabase` offre Postgres gestito con DX rapida per beta/test.
- `Render` e una scelta pragmatica per `FastAPI` senza refactor.
- `Vercel Functions` non e il fit ideale per questo backend (scheduler + logica pricing/historical).

## Cosa significa "ambiente di test" (pratico)
Non serve scalare, ma deve essere:
- stabile
- raggiungibile
- simile alla produzione

L'obiettivo non e solo "funziona", ma riuscire a testare in modo realistico:
- flussi utente
- affidabilita dati
- comportamento auth/CORS

## Backend: opzioni e raccomandazione
### Opzioni possibili
1. `Render` (consigliato per partire)
- setup semplice
- env vars facili
- adatto a FastAPI
- scheduler gestibile

2. `Railway`
- setup rapido
- buona DX
- attenzione a costi/runtime nel tempo

3. `Fly.io`
- piu controllo
- piu complessita operativa

4. `Vercel Functions` (non consigliato qui)
- richiede adattamenti importanti
- non ideale per scheduler/lifespan backend attuale

### Raccomandazione
Per `Valore365` in test: `Render`.

## Impatti sul codice attuale (importanti)
### 1. Frontend con base path `/api` hardcoded
Il frontend usa `'/api'` in `src/frontend/valore-frontend/src/services/api.ts`.

Implicazioni su Vercel:
- serve un `rewrite/proxy` `/api/*` verso backend esterno
- oppure (consigliato) aggiungere `VITE_API_BASE_URL` con fallback a `/api`

Consiglio:
- introdurre `VITE_API_BASE_URL`
- mantenere fallback a `/api` per compatibilita locale/Docker

### 2. Scheduler backend
Lo scheduler parte nel `lifespan` FastAPI.

In ambiente test:
- inizialmente tenerlo `OFF`
- attivarlo solo dopo aver stabilizzato CRUD/auth/dashboard
- evitare piu istanze backend con scheduler attivo (duplicazione job)

## Supabase: cosa comporta per il progetto
Hai gia schema SQL e migrazioni, quindi Supabase e quasi plug-and-play.

Passi:
- creare progetto Supabase
- recuperare connection string (meglio pooled se disponibile)
- applicare `schema.sql`, `seed.sql` e migrazioni
- configurare `DATABASE_URL` nel backend host

Nota:
- Supabase usa Postgres standard, quindi il DB attuale e compatibile salvo edge case specifici.

## Ambienti consigliati (minimo)
### 1. `local`
- Docker Compose / localhost
- Clerk `OFF`

### 2. `test` (cloud)
- Vercel + Supabase + Render
- Clerk `ON` (se vuoi test auth reale)
- scheduler `OFF` inizialmente

Poi eventualmente:
### 3. `prod`
- separato da `test`

## Checklist pratica di setup (ambiente test)
### 1. Supabase
- creare progetto DB
- eseguire schema + seed + migrazioni
- salvare `DATABASE_URL`

### 2. Backend su Render (o Railway)
Deploy di `src/backend`.

Env vars minime consigliate:
- `APP_ENV=prod`
- `DATABASE_URL=<supabase connection string>`
- `FINANCE_PROVIDER=yfinance`
- `PRICE_SCHEDULER_ENABLED=false` (all'inizio)

Se auth Clerk attiva:
- `CLERK_AUTH_ENABLED=true`
- `CLERK_JWKS_URL=<jwks clerk>`
- `CLERK_AUTHORIZED_PARTIES=https://<dominio-vercel>`
- `CORS_ALLOWED_ORIGINS=https://<dominio-vercel>`

### 3. Frontend su Vercel
Deploy di `src/frontend/valore-frontend`.

Env vars:
- `VITE_CLERK_PUBLISHABLE_KEY` (se Clerk attivo)
- (consigliato) `VITE_API_BASE_URL=https://<backend-domain>` se fai patch frontend

Se non fai patch frontend:
- configurare rewrite `/api` su Vercel verso backend esterno

## Rischi principali da gestire
- `CORS` backend verso dominio Vercel
- mismatch `Clerk authorized parties (azp)` vs dominio frontend
- frontend `/api` senza rewrite (se non aggiungi `VITE_API_BASE_URL`)
- scheduler duplicato se backend scala su piu istanze
- affidabilita/rate limit del provider (`yfinance`)

## Strategia consigliata (riduce complessita)
1. Portare online `frontend + backend + DB` con Clerk `OFF`
2. Verificare flussi core (portfolio/transazioni/dashboard)
3. Attivare Clerk
4. Attivare scheduler automatico solo dopo stabilizzazione
5. Aggiungere monitoring (es. Sentry)

## Decisione raccomandata per il backend
Per il tuo caso (Valore365): `Render` per ambiente di test.

Motivi:
- supporto Python/FastAPI immediato
- basso attrito operativo
- sufficiente per beta/test SaaS

## Prossimi step suggeriti
1. Preparare piano deploy dettagliato `Vercel + Supabase + Render` specifico per Valore365
2. Elencare env vars finali per ciascun servizio
3. Patch frontend per supportare `VITE_API_BASE_URL` (fallback a `/api`)
4. (Opzionale) Configurare rewrite Vercel se non si vuole patchare subito il frontend
