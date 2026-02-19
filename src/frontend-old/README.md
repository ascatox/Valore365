# Frontend - Valore365

Bootstrap iniziale con React + Vite + TypeScript.

## Setup
1. Copiare `.env.example` in `.env`
2. `npm install`
3. `npm run dev`

## Config
- `VITE_API_BASE_URL` (default: `http://localhost:8000`)
- `VITE_DEFAULT_PORTFOLIO_ID` (default: `1`)
- `VITE_CLERK_PUBLISHABLE_KEY` (obbligatoria per login Clerk)

## Stato attuale
- Login pagina dedicata con Clerk (`SignedOut` + `SignIn`) e user menu (`UserButton`)
- Form rapido \"Aggiungi Titolo\" da FE:
  - crea asset (`POST /assets`)
  - crea mapping provider (`POST /asset-provider-symbols`)
  - opzionale buy iniziale (`POST /transactions`)
- autocomplete su symbol con ricerca asset gia presenti (`GET /assets/search`)
- validazione client-side su symbol, currency, ISIN, exchange code e campi buy
- pulsanti operativi dashboard:
  - `Refresh prezzi ora` (`POST /prices/refresh`)
  - `Backfill 1Y` (`POST /prices/backfill-daily`)
- notifiche toast (success/error/info) al posto dei messaggi statici di esito
- Dashboard base con fetch di:
  - `/portfolios/{id}/summary`
  - `/portfolios/{id}/positions`
  - `/portfolios/{id}/timeseries?range=1y&interval=1d`
- Tabella posizioni
- KPI principali

Prossimo step consigliato: integrazione grafici con ECharts/Recharts.
