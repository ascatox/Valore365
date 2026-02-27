# Piano Deploy Test - Valore365 (Vercel + Supabase + Render)

## Contesto
Valore365 è un'app portfolio SaaS (React + FastAPI + PostgreSQL). Attualmente funziona solo in locale via Docker Compose. L'obiettivo è portarla in un ambiente di test cloud per validare auth, CRUD, pricing e dashboard in modo realistico.

## Strategia: deploy incrementale in 4 fasi
1. DB online → 2. Backend online → 3. Frontend online → 4. Attivazione auth

---

## Modifiche al codice (già applicate)

### 1. Frontend: `VITE_API_BASE_URL`

**File:** `src/frontend/valore-frontend/src/services/api.ts` (riga 1)

```ts
// Prima
const API_URL = '/api';

// Dopo
const API_URL = import.meta.env.VITE_API_BASE_URL || '/api';
```

Permette al frontend di puntare al backend Render in test, mantenendo compatibilità locale.

### 2. Frontend: `.env.example`

**File nuovo:** `src/frontend/valore-frontend/.env.example`

```env
# Backend API base URL (leave empty for local dev with proxy)
VITE_API_BASE_URL=

# Clerk publishable key (leave empty to disable auth)
VITE_CLERK_PUBLISHABLE_KEY=
```

### 3. Vercel config

**File nuovo:** `src/frontend/valore-frontend/vercel.json`

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://<RENDER_BACKEND_URL>/api/:path*" }
  ]
}
```

> **TODO:** Sostituire `<RENDER_BACKEND_URL>` con l'URL reale di Render dopo il deploy del backend.

Il rewrite è un fallback nel caso `VITE_API_BASE_URL` non venga impostato.

### 4. Render Blueprint

**File nuovo:** `render.yaml` (root del progetto)

```yaml
services:
  - type: web
    name: valore365-api
    runtime: python
    region: frankfurt
    rootDir: src/backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: APP_ENV
        value: prod
      - key: DATABASE_URL
        sync: false
      - key: FINANCE_PROVIDER
        value: yfinance
      - key: PRICE_SCHEDULER_ENABLED
        value: "false"
      - key: CLERK_AUTH_ENABLED
        value: "false"
      - key: CORS_ALLOWED_ORIGINS
        sync: false
      - key: CLERK_JWKS_URL
        sync: false
      - key: CLERK_AUTHORIZED_PARTIES
        sync: false
```

### 5. CORS backend (nessuna modifica necessaria)

Già configurato in:
- `src/backend/app/config.py:29-37` — legge `CORS_ALLOWED_ORIGINS` come CSV
- `src/backend/app/main.py:94` — in `APP_ENV=prod` usa la lista da env var

Basta impostare la env var su Render con il dominio Vercel.

---

## Env vars per servizio (da configurare manualmente)

### Supabase
- Creare progetto → ottenere `DATABASE_URL` (connection pooler consigliato)
- Eseguire `database/schema.sql` + `database/seed.sql` + tutte le migrazioni in ordine

### Render (backend)
```
APP_ENV=prod
DATABASE_URL=<supabase-connection-string>
FINANCE_PROVIDER=yfinance
PRICE_SCHEDULER_ENABLED=false
CLERK_AUTH_ENABLED=false
CORS_ALLOWED_ORIGINS=https://<dominio-vercel>
```

### Vercel (frontend)
```
VITE_API_BASE_URL=https://<dominio-render>
VITE_CLERK_PUBLISHABLE_KEY=           # vuoto inizialmente
```

---

## Ordine di deploy consigliato

1. **Supabase**: creare DB, applicare schema/seed/migrazioni
2. **Render**: deploy backend, configurare env vars, verificare `/api/health` o endpoint simile
3. **Vercel**: deploy frontend, configurare env vars, verificare che la dashboard carichi
4. **Test flussi**: portfolio CRUD, transazioni, dashboard
5. **Clerk ON**: attivare auth su backend + frontend
6. **Scheduler ON**: `PRICE_SCHEDULER_ENABLED=true` solo dopo stabilizzazione

---

## Checklist di verifica

- [ ] Frontend su Vercel carica senza errori console
- [ ] Chiamate API dal frontend raggiungono il backend Render (no CORS error)
- [ ] CRUD portfolio funziona (crea, leggi, modifica, elimina)
- [ ] Transazioni si salvano e appaiono in dashboard
- [ ] Nessun errore 401/403 con Clerk OFF (dev-user mode)
- [ ] (Dopo fase 5) Login Clerk funziona, dati isolati per utente

---

## Riepilogo file modificati

| File | Azione | Descrizione |
|------|--------|-------------|
| `src/frontend/valore-frontend/src/services/api.ts` | Edit | `VITE_API_BASE_URL` con fallback `/api` |
| `src/frontend/valore-frontend/.env.example` | Nuovo | Documentazione env vars frontend |
| `src/frontend/valore-frontend/vercel.json` | Nuovo | Config deploy Vercel + rewrite API |
| `render.yaml` | Nuovo | Blueprint Render per backend FastAPI |
