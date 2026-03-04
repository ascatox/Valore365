# Analisi di Sicurezza — Valore365

**Data:** 2026-03-04

---

## Frontend — Riepilogo

| Severità | # | Dettagli |
|---|---|---|
| **CRITICAL** | 0 | — |
| **HIGH** | 1 | Dipendenze build vulnerabili |
| **MEDIUM** | 3 | Auth disattivabile, CORS `*` in dev, nessun CSP |
| **LOW** | 5 | JWKS URL nel repo, credenziali DB in docker-compose, URL backend esposto, validazione input minima, errori verbosi |
| **INFO** | 6 | Token handling OK, nessun XSS, nessun console.log, CSRF OK, localStorage sicuro, upload OK |

### HIGH — Dipendenze build vulnerabili (rollup, minimatch)

`npm audit` rileva 5 CVE:

| Package | Severità | Descrizione | Impatto |
|---------|----------|-------------|---------|
| **rollup** 4.0.0-4.58.0 | HIGH | Arbitrary File Write via Path Traversal (GHSA-mw96-cpmx-2vgc) | Solo build-time |
| **minimatch** <=3.1.3 | HIGH | ReDoS via repeated wildcards (3 CVE) | Solo build-time (eslint dep) |
| **esbuild** <=0.24.2 | MODERATE | Dev server abilita richieste cross-origin (GHSA-67mh-4wv8-2f99) | Solo dev server |
| **vite** 0.11.0-6.1.6 | MODERATE | Dipende da esbuild vulnerabile | Solo dev server |
| **ajv** <6.14.0 | MODERATE | ReDoS con opzione `$data` | Solo build-time |

Tutte le vulnerabilità sono in dipendenze di **build-time o dev-server**, non nel codice runtime. Risolvibili con `npm audit fix`.

### MEDIUM — L'autenticazione si disattiva se manca la env var

- **File:** `src/frontend/valore-frontend/src/components/AuthGuard.tsx:4`
- Se `VITE_CLERK_PUBLISHABLE_KEY` è vuota, l'auth viene bypassata e il backend usa un utente hardcoded `dev-user`.
- **Rischio:** Se in produzione la variabile non viene settata, l'app è accessibile senza autenticazione.

### MEDIUM — Nessun Content Security Policy né security headers

- **File:** `index.html`, `nginx.conf`, `nginx.prod.conf`
- Mancano completamente: CSP, `X-Frame-Options`, `X-Content-Type-Options`, HSTS, `Referrer-Policy`, `Permissions-Policy`.
- Nessuna difesa in profondità contro clickjacking e injection.

**Header consigliati per nginx.prod.conf:**

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.clerk.accounts.dev; img-src 'self' data:; font-src 'self';" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
```

### MEDIUM — CORS aperto in dev

- **File:** `src/backend/app/main.py:120-127`
- `allow_origins=["*"]` in modalità dev. La config di produzione è correttamente restrittiva.

### LOW — JWKS URL nel repo

- **File:** `render.yaml:37`
- L'URL JWKS è committato nel version control. Rivela il nome dell'istanza Clerk e agevola la ricognizione.

### LOW — Credenziali DB default in docker-compose

- **File:** `docker-compose.yml:6-8,26`
- `POSTGRES_USER: postgres`, `POSTGRES_PASSWORD: postgres` hardcoded. Solo per sviluppo locale, ma andrebbero parametrizzate.

### LOW — URL backend esposto in vercel.json

- **File:** `src/frontend/valore-frontend/vercel.json:6`
- `https://valore365.onrender.com` rivela l'infrastruttura backend.

### LOW — Validazione input minima

- **File:** `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:530-545`
- Validazione client-side basilare, la maggior parte è delegata al backend (pattern accettabile se il backend valida correttamente).

### LOW — Errori mostrati all'utente

- **File:** `src/frontend/valore-frontend/src/services/api.ts:491-504`
- I messaggi di errore del backend possono essere visualizzati direttamente. Se il backend restituisce errori verbosi, l'utente li vede.

### Punti positivi del Frontend

- Nessun uso di `dangerouslySetInnerHTML`, `eval()`, `innerHTML` — **nessun vettore XSS**
- Token JWT gestiti correttamente via header Authorization, mai in URL o localStorage
- Nessun `console.log` nel codice
- `encodeURIComponent()` usato correttamente nei parametri query
- Solo preferenze UI in localStorage, nessun dato sensibile
- Nessun cookie manipolato direttamente (`document.cookie` non usato)

---

## Backend — Riepilogo

| Severità | # | Dettagli |
|---|---|---|
| **CRITICAL** | 1 | Auth disabilitata di default |
| **HIGH** | 5 | No rate limiting, JWT audience non verificata, CORS `*` in dev, DoS via market quotes, DoS via backfill |
| **MEDIUM** | 11 | Nessun limite CSV, no pagination, credenziali DB default, CORS regex troppo larga, race condition, thread illimitati, ecc. |
| **LOW** | 7 | SQL dinamico (safe ma fragile), PAC prezzo arbitrario, CSV filename, ecc. |
| **INFO** | 5 | Protezione IDOR solida, no debug mode, Pydantic ben configurato |

### CRITICAL — Auth completamente disabilitata di default

- **File:** `src/backend/app/auth.py:62`
- `CLERK_AUTH_ENABLED` è `false` di default in `config.py:35`.
- Se la produzione non setta esplicitamente questa variabile, tutte le richieste passano come `dev-user` senza alcun token.

```python
if not settings.clerk_auth_enabled:
    return AuthContext(user_id="dev-user", org_id=None, claims={})
```

**Mitigazione:** Aggiungere un check allo startup che rifiuta di avviare l'app con auth disabilitata quando `APP_ENV=prod`.

### HIGH — Nessun rate limiting

- Tutto il backend è privo di rate limiting.
- Endpoint critici: `/api/prices/refresh`, `/api/prices/backfill-daily`, `/api/markets/quotes`, `/api/portfolios/{id}/csv-import/preview`.
- Possibile abuso per DoS o esaurimento delle quote API esterne.

**Mitigazione:** Aggiungere `slowapi` o middleware equivalente.

### HIGH — JWT `aud` non verificato

- **File:** `src/backend/app/auth.py:76`
- `verify_aud: False` — un JWT emesso per un'altra applicazione Clerk potrebbe essere accettato.

```python
"options": {"require": ["exp", "iat", "sub"], "verify_aud": False},
```

**Mitigazione:** Settare `verify_aud: True` e configurare l'audience attesa.

### HIGH — DoS via `/api/markets/quotes`

- **File:** `src/backend/app/main.py:1204-1244`
- 14 chiamate API sequenziali con sleep. Una singola richiesta può durare >2 minuti e bloccare il worker.
- Richieste multiple concorrenti possono esaurire il thread pool di uvicorn.

### HIGH — DoS via `/api/prices/backfill-daily`

- **File:** `src/backend/app/main.py:522-545`
- Fetch storico illimitato per tutti gli asset di un portfolio (fino a 2000 giorni).
- Decine di chiamate API esterne senza concurrency limit.

### MEDIUM — Thread daemon illimitati

- **File:** `src/backend/app/main.py:453-457, 756-760, 1091-1095`
- Ogni creazione transazione e upsert target allocation spawna un thread daemon tramite `threading.Thread`.
- Nessun thread pool. Creazioni rapide possono generare centinaia di thread.

```python
threading.Thread(
    target=historical_service.backfill_single_asset,
    kwargs={"asset_id": payload.asset_id, "portfolio_id": payload.portfolio_id},
    daemon=True,
).start()
```

**Mitigazione:** Usare `concurrent.futures.ThreadPoolExecutor` con limite.

### MEDIUM — Race condition nel rebalance

- **File:** `src/backend/app/main.py:1040-1104`
- Transazioni multiple create in loop con `engine.begin()` separati, senza lock.
- Due rebalance concorrenti sullo stesso portfolio possono creare transazioni conflittuali.

### MEDIUM — CORS regex troppo larga in produzione

- **File:** `src/backend/app/main.py:131`
- `https://.*\.vercel\.app` permette a **qualsiasi** deployment Vercel di fare richieste cross-origin con `allow_credentials=True`.

**Mitigazione:** Restringere al dominio specifico del frontend (es. `https://valore365.*\.vercel\.app`).

### MEDIUM — Nessun limite dimensione CSV

- **File:** `src/backend/app/main.py:1289-1301`
- `file.read()` senza size check. File enormi possono causare OOM.

**Mitigazione:** `if len(content) > 10_000_000: raise HTTPException(413, "File too large")`.

### MEDIUM — Nessun `max_length` su `notes`

- **File:** `src/backend/app/models.py:68, 503`
- Campo testo senza limite su `TransactionCreate` e `CashMovementCreate`. Possibile storage abuse.

**Mitigazione:** `notes: str | None = Field(default=None, max_length=2000)`.

### MEDIUM — Validation error espone dettagli interni

- **File:** `src/backend/app/main.py:146`
- `str(exc)` su `RequestValidationError` rivela nomi e tipi dei campi Pydantic ad eventuali attaccanti.

### MEDIUM — Nessun limite paginazione

- Endpoint come `GET /portfolios/{id}/transactions` e `GET /portfolios/{id}/positions` restituiscono tutti i risultati senza paginazione.

### MEDIUM — Nessun body size limit

- FastAPI/Starlette non impone un limite massimo al body delle richieste. Payload JSON enormi possono essere inviati a qualsiasi endpoint.

### MEDIUM — Nessuna validazione somma pesi target allocation

- L'endpoint `upsert_portfolio_target_allocation` non verifica che la somma dei pesi sia 100%. Un utente può settare allocazioni totali al 500%.

### MEDIUM — Jinja2 3.1.4 potenzialmente obsoleta

- **File:** `src/backend/requirements.txt:11`
- Non usata direttamente dal codice, probabilmente dipendenza transitiva. Aggiornare all'ultima versione.

### LOW — SQL dinamico (safe ma fragile)

- **File:** `src/backend/app/repository.py:1491-1493`
- Column names interpolati tramite f-string, ma derivati da campi Pydantic hardcoded. Safe in pratica, fragile se si aggiungono campi user-controllati.

### LOW — PAC prezzo arbitrario

- **File:** `src/backend/app/main.py:1441-1498`
- `confirm_pac_execution` accetta un `price` dall'utente senza validazione contro il prezzo di mercato.

### LOW — CSV data loggata a livello INFO

- **File:** `src/backend/app/csv_service.py:90, 211, 225, 262-265`
- Dati finanziari degli utenti loggati in chiaro. Rischio in sistemi di log aggregation.

### LOW — HTTPS non forzato

- **File:** `src/backend/Dockerfile`
- Uvicorn senza TLS. Presumibilmente gestito dal reverse proxy, ma mancano header HSTS.

### Punti positivi del Backend

- **Protezione IDOR solida:** `owner_user_id` verificato su tutte le operazioni portfolio
- **Tutte le query SQL usano parametri named** (`:param_name`)
- **Pydantic models ben vincolati** con `Field()`, pattern regex, ge/le
- **Nessun debug mode** in produzione
- **Nessun path traversal** possibile

---

## Raccomandazioni prioritarie

| # | Azione | Severità | Effort |
|---|---|---|---|
| 1 | Forzare `CLERK_AUTH_ENABLED=true` in produzione con check allo startup | CRITICAL | Basso |
| 2 | Abilitare `verify_aud` nel JWT e configurare l'audience attesa | HIGH | Basso |
| 3 | Aggiungere rate limiting (`slowapi`) su tutti gli endpoint, specialmente quelli con chiamate esterne | HIGH | Medio |
| 4 | Limitare dimensione upload CSV (es. max 10MB) e numero righe | HIGH | Basso |
| 5 | Usare un `ThreadPoolExecutor` invece di `threading.Thread` illimitati | HIGH | Medio |
| 6 | Aggiungere security headers (CSP, X-Frame-Options, HSTS, X-Content-Type-Options) in nginx | MEDIUM | Basso |
| 7 | Restringere CORS regex in produzione al dominio specifico del frontend | MEDIUM | Basso |
| 8 | Aggiungere paginazione agli endpoint che restituiscono liste | MEDIUM | Medio |
| 9 | Sanitizzare i messaggi di errore di validazione prima di inviarli al client | MEDIUM | Basso |
| 10 | `npm audit fix` per le vulnerabilità build-time del frontend | MEDIUM | Basso |
