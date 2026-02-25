# Frontend - Valore365

Frontend SPA `React + Vite + TypeScript + Mantine` per dashboard, gestione portfolio/transazioni e impostazioni.

## Stack
- React 18
- Vite 5
- TypeScript
- Mantine 7
- Recharts
- React Router
- Clerk (opzionale, autenticazione)

## Funzionalita implementate
- Layout applicativo con navbar, refresh globale e toggle tema
- Dashboard con tab `Panoramica`, `Posizioni`, `Analisi`
- Selezione portfolio persistita in `localStorage`
- Refresh dati dashboard via evento globale (`valore365:refresh-dashboard`)
- Pull-to-refresh su mobile
- Pagina `Portfolio` con CRUD portfolio, target allocation, gestione asset target (ricerca DB + provider) e CRUD transazioni
- Pagina `Settings` (UI impostazioni generali/fiscali/sicurezza)
- Auth opzionale con Clerk (`AuthGuard` + `ClerkTokenBridge`)

## Requisiti
- Node.js 20+ (consigliato)
- Backend Valore365 disponibile su `http://localhost:8000` in locale

## Avvio locale
Da `src/frontend/valore-frontend`:

```bash
npm install
npm run dev
```

Apri:
- `http://localhost:5173`

Il dev server Vite proxya `/api` verso `http://localhost:8000` (vedi `vite.config.ts`).

## Build e lint
```bash
npm run build
npm run lint
```

Output build:
- `dist/`

## Configurazione
### API backend
Il client usa `'/api'` come base path (`src/services/api.ts`).

Questo significa:
- locale: funziona tramite proxy Vite
- Docker frontend: funziona tramite proxy Nginx (`nginx.conf`)
- deploy separato frontend/backend: serve un rewrite/proxy `/api` oppure una modifica del client API per usare un URL configurabile

### Clerk (opzionale)
Variabile supportata:
- `VITE_CLERK_PUBLISHABLE_KEY`

Comportamento:
- assente: app senza autenticazione frontend
- presente: `AuthGuard` forza login e `ClerkTokenBridge` inoltra il bearer token alle chiamate API

## Docker
Il `Dockerfile`:
- builda l'app con Vite
- serve `dist/` con Nginx
- usa `nginx.conf` con proxy `/api` verso `api-dev:8000`

Build arg supportato:
- `VITE_CLERK_PUBLISHABLE_KEY` (opzionale)

## Struttura principale
- `src/App.tsx`: shell, routing, refresh globale
- `src/main.tsx`: bootstrap Mantine + Clerk provider opzionale
- `src/services/api.ts`: client API + tipi TypeScript
- `src/pages/Dashboard.page.tsx`: dashboard e tab analitici
- `src/pages/Portfolio.page.tsx`: portfolio, target allocation e transazioni
- `src/pages/Settings.page.tsx`: impostazioni (UI)

## Note operative
- Il backend deve esporre le route sotto `/api`.
- Se abiliti Clerk lato frontend, abilita anche il backend per una validazione end-to-end coerente.
