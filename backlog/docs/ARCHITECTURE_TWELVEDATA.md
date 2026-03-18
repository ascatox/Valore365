# Istruzioni per Gemini (Architettura + API Twelve Data)

## Obiettivo
- Allineare tutte le chiamate Twelve Data ai parametri corretti.
- Garantire che il backend sia l’unico punto di accesso all’API (mai dal frontend).
- Supportare aggiornamento manuale, storicizzazione daily, retention 2 anni, base currency EUR.

## 1) Mappa chiamate Twelve Data attuali nel backend
Analizza:
- `src/backend/app/finance_client.py`
- `src/backend/app/pricing_service.py`
- `src/backend/app/historical_service.py`

Endpoint usati:
- `symbol_search` → autocomplete
- `quote` → prezzi realtime
- `time_series` → daily bars (asset)
- `time_series` su coppia FX → daily FX

## 2) Parametri corretti da usare per Twelve Data
In base alla doc Twelve Data:
- `symbol_search`
  - Parametri consigliati: `symbol`, opzionali `exchange`, `country`, `mic_code`.
- `quote`
  - Parametri: `symbol`.
- `time_series` (daily asset)
  - Parametri corretti:
    - `symbol`
    - `interval=1day`
    - Usare `start_date` e `end_date` per range preciso (2 anni)
    - Usare `timezone=UTC` per uniformità
    - `order=asc` per ordinamento cronologico
    - `outputsize` solo se non si usano start/end
- `time_series` (FX daily)
  - Stessi parametri di `time_series`
  - `symbol` nel formato `FROM/TO` es: `USD/EUR`

Nota: se si usano `start_date`/`end_date`, evitare `outputsize` per non introdurre ambiguità.

## 3) Strategia dati e retention
- Usare solo daily bars (`price_bars_1d`) e FX daily (`fx_rates_1d`).
- Retention 2 anni:
  - Dopo ogni backfill o refresh daily, pulire DB:
    - `delete from price_bars_1d where price_date < current_date - interval '730 days'`
    - `delete from fx_rates_1d where price_date < current_date - interval '730 days'`

## 4) Aggiornamento manuale
- Pulsante “Aggiorna” nel frontend → endpoint backend.
- Backend deve:
  1. Chiamare Twelve Data `time_series` per ogni asset con `start_date=today-1` e `end_date=today` (o 3 giorni per gap).
  2. Salvare daily bars in DB.
  3. Aggiornare FX rates per tutte le valute non EUR presenti.

Nessuna chiamata diretta a Twelve Data dal frontend.

## 5) Uso API in frontend (design)
Il frontend deve leggere solo dal DB tramite backend:
- Autocomplete: `/api/symbols?q=...` → Twelve Data `symbol_search`
- Dashboard:
  - Summary → `/api/portfolios/{id}/summary`
  - Timeseries → `/api/portfolios/{id}/timeseries?range=1y&interval=1d`
  - Allocation → `/api/portfolios/{id}/allocation`
- Portfolio:
  - Positions → `/api/portfolios/{id}/positions`
- Aggiorna:
  - `/api/prices/backfill-daily?portfolio_id=...&days=730` (o endpoint dedicato `refresh-daily`)

## 6) Controlli / error handling
- Validare che la base currency sia EUR (hardcoded a livello business).
- Se Twelve Data non restituisce valori:
  - log + warning, non interrompere l’intero batch.
- Rate limit:
  - introdurre delay configurabile fra simboli.

## 7) Deliverable attesi da Gemini
1. Elenco puntuale di chiamate Twelve Data con parametri corretti.
2. Proposta di endpoint backend (se necessario `refresh-daily` separato).
3. Flusso aggiornamento manuale con retention 2 anni.
4. Tabella finale: endpoint FE → BE → Twelve Data.

## 8) Analisi Frontend e mapping API per pagina
Pagine presenti:
- `src/frontend/valore-frontend/src/pages/Dashboard.page.tsx`
- `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx`
- `src/frontend/valore-frontend/src/pages/Settings.page.tsx`
- `src/frontend/valore-frontend/src/services/api.ts`

### Dashboard
Componenti e dati attesi:
- KPI cards (patrimonio, P&L, costi) → **`GET /api/portfolios/{id}/summary`**
  - Il backend calcola tutto da DB locale.
- Grafico storico (AreaChart YTD/1Y) → **`GET /api/portfolios/{id}/timeseries?range=1y&interval=1d`**
- Allocazione (RingProgress) → **`GET /api/portfolios/{id}/allocation`**
- Top movers (tabella) → derivabile da positions + prezzi daily
  - **`GET /api/portfolios/{id}/positions`** e calcolo client-side dei top movers.
- Pulsante “Aggiorna” → **`POST /api/prices/backfill-daily?portfolio_id={id}&days=3`**
  - 3 giorni per coprire gap weekend/holiday; retention e cleanup gestiti dal backend.

### Portfolio
Componenti e dati attesi:
- Tabella asset e P&L → **`GET /api/portfolios/{id}/positions`**
- Drawer “Nuova Transazione”
  - Autocomplete simboli → **`GET /api/symbols?q=...`**
  - Creazione asset (se non esiste) → **`POST /api/assets`**
  - Mapping provider symbol → **`POST /api/asset-provider-symbols`**
  - Inserimento transazione → **`POST /api/transactions`**

### Settings
Componenti e dati attesi (per ora solo EUR):
- Valuta base fissa EUR → nessuna chiamata (statico).
- Target allocation / fiscalità → al momento UI-only (opzionale endpoint futuro).
  - Possibile futuro: `GET/PUT /api/portfolios/{id}/targets`

### Servizi FE
`src/frontend/valore-frontend/src/services/api.ts`:
- Attualmente usa `/api/symbols` → corretto con prefisso API.
- Estendere con:
  - `getSummary(portfolioId)`
  - `getTimeseries(portfolioId)`
  - `getAllocation(portfolioId)`
  - `getPositions(portfolioId)`
  - `refreshDaily(portfolioId, days=3)`

## 9) Regole chiave per FE
- Il frontend non deve mai chiamare Twelve Data direttamente.
- Tutti i dati visibili in pagina devono provenire dal DB locale via backend.
- Il tasto “Aggiorna” deve solo triggerare il backend; poi ricaricare i dati locali.
