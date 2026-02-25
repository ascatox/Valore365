│ Piano: Tab "Mercati" nella Dashboard                                                                                                                                           │
     │                                                                                                                                                                                │
     │ Contesto                                                                                                                                                                       │
     │                                                                                                                                                                                │
     │ La dashboard ha 3 tab (Panoramica, Posizioni, Analisi). Si vuole aggiungere un 4° tab "Mercati" che mostri in tempo reale i principali indici internazionali, materie prime e  │
     │ criptovalute. Nessun dato salvato su DB — solo fetch live dal finance client (yfinance/TwelveData).                                                                            │
     │                                                                                                                                                                                │
     │ File da modificare/creare                                                                                                                                                      │
     │                                                                                                                                                                                │
     │ ┌─────┬──────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────┐                        │
     │ │  #  │                             File                             │                                     Azione                                     │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 1   │ src/backend/app/finance_client.py                            │ Aggiungere ProviderMarketQuote + metodo get_market_quote() a entrambi i client │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 2   │ src/backend/app/models.py                                    │ Aggiungere 3 Pydantic models per la response                                   │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 3   │ src/backend/app/main.py                                      │ Aggiungere costante MARKET_SYMBOLS + endpoint GET /api/markets/quotes          │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 4   │ src/frontend/.../services/api.ts                             │ Aggiungere interfacce TS + funzione getMarketQuotes()                          │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 5   │ src/frontend/.../components/dashboard/hooks/useMarketData.ts │ Nuovo — hook standalone per fetch lazy                                         │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 6   │ src/frontend/.../components/dashboard/tabs/MercatiTab.tsx    │ Nuovo — componente tab con card grid                                           │                        │
     │ ├─────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┤                        │
     │ │ 7   │ src/frontend/.../pages/Dashboard.page.tsx                    │ Aggiungere tab "Mercati" + integrare hook                                      │                        │
     │ └─────┴──────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────┘                        │
     │                                                                                                                                                                                │
     │ ---                                                                                                                                                                            │
     │ Step 1 — Backend: ProviderMarketQuote + get_market_quote()                                                                                                                     │
     │                                                                                                                                                                                │
     │ File: src/backend/app/finance_client.py                                                                                                                                        │
     │                                                                                                                                                                                │
     │ Aggiungere dataclass dopo ProviderSymbol (riga ~53):                                                                                                                           │
     │ @dataclass                                                                                                                                                                     │
     │ class ProviderMarketQuote:                                                                                                                                                     │
     │     symbol: str                                                                                                                                                                │
     │     price: float | None                                                                                                                                                        │
     │     previous_close: float | None                                                                                                                                               │
     │     ts: datetime                                                                                                                                                               │
     │                                                                                                                                                                                │
     │ YahooFinanceClient (riga ~382) — nuovo metodo get_market_quote():                                                                                                              │
     │ - Usa ticker.fast_info per ottenere last_price e previous_close                                                                                                                │
     │ - Fallback a ticker.history(period='5d') se fast_info fallisce (stessa logica di get_quote esistente)                                                                          │
     │ - Non lancia eccezioni — ritorna price=None se non disponibile                                                                                                                 │
     │                                                                                                                                                                                │
     │ TwelveDataClient (riga ~55) — nuovo metodo get_market_quote():                                                                                                                 │
     │ - Delega a self.get_quote(), wrappa in ProviderMarketQuote con previous_close=None                                                                                             │
     │                                                                                                                                                                                │
     │ Step 2 — Backend: Pydantic response models                                                                                                                                     │
     │                                                                                                                                                                                │
     │ File: src/backend/app/models.py (append in fondo)                                                                                                                              │
     │                                                                                                                                                                                │
     │ - MarketQuoteItem: symbol, name, price, previous_close, change, change_pct, ts, error (tutti nullable tranne symbol/name)                                                      │
     │ - MarketCategory: category (key), label (display), items                                                                                                                       │
     │ - MarketQuotesResponse: categories list                                                                                                                                        │
     │                                                                                                                                                                                │
     │ Step 3 — Backend: Endpoint + costante simboli                                                                                                                                  │
     │                                                                                                                                                                                │
     │ File: src/backend/app/main.py                                                                                                                                                  │
     │                                                                                                                                                                                │
     │ Costante MARKET_SYMBOLS (dict con 3 chiavi):                                                                                                                                   │
     │ - indices: ^GSPC S&P 500, ^DJI Dow Jones, ^IXIC Nasdaq, ^STOXX50E Euro Stoxx 50, FTSEMIB.MI FTSE MIB, ^FTSE FTSE 100, ^GDAXI DAX, ^N225 Nikkei 225                             │
     │ - commodities: GC=F Oro, SI=F Argento, CL=F Petrolio WTI                                                                                                                       │
     │ - crypto: BTC-USD Bitcoin, ETH-USD Ethereum, SOL-USD Solana                                                                                                                    │
     │                                                                                                                                                                                │
     │ Endpoint GET /api/markets/quotes:                                                                                                                                              │
     │ - Protetto con require_auth (come tutti gli altri endpoint)                                                                                                                    │
     │ - Itera categorie/simboli, chiama finance_client.get_market_quote() per ciascuno                                                                                               │
     │ - Calcola change = price - previous_close e change_pct se entrambi disponibili                                                                                                 │
     │ - Errori per singolo simbolo catturati → riportati nel campo error dell'item (partial failure, no 500)                                                                         │
     │ - Rispetta settings.finance_symbol_request_delay_seconds tra le chiamate                                                                                                       │
     │ - Nessuna interazione con DB                                                                                                                                                   │
     │ - Import nuovi models: MarketQuoteItem, MarketCategory, MarketQuotesResponse                                                                                                   │
     │                                                                                                                                                                                │
     │ Step 4 — Frontend: API types + fetch function                                                                                                                                  │
     │                                                                                                                                                                                │
     │ File: src/frontend/valore-frontend/src/services/api.ts                                                                                                                         │
     │                                                                                                                                                                                │
     │ Aggiungere in fondo:                                                                                                                                                           │
     │ - Interfacce MarketQuoteItem, MarketCategory, MarketQuotesResponse                                                                                                             │
     │ - Funzione getMarketQuotes(): Promise<MarketQuotesResponse> che chiama apiFetch('/markets/quotes')                                                                             │
     │                                                                                                                                                                                │
     │ Step 5 — Frontend: Hook useMarketData                                                                                                                                          │
     │                                                                                                                                                                                │
     │ File: src/frontend/valore-frontend/src/components/dashboard/hooks/useMarketData.ts (nuovo)                                                                                     │
     │                                                                                                                                                                                │
     │ Hook standalone (non dipende da portfolio selezionato):                                                                                                                        │
     │ - State: data: MarketQuotesResponse | null, loading, error, loaded                                                                                                             │
     │ - Espone fetchMarketData() chiamato dal componente tab                                                                                                                         │
     │ - Flag loaded evita re-fetch quando si torna al tab                                                                                                                            │
     │                                                                                                                                                                                │
     │ Step 6 — Frontend: Componente MercatiTab                                                                                                                                       │
     │                                                                                                                                                                                │
     │ File: src/frontend/valore-frontend/src/components/dashboard/tabs/MercatiTab.tsx (nuovo)                                                                                        │
     │                                                                                                                                                                                │
     │ - Riceve MarketDataState come props (pattern coerente con gli altri tab che ricevono data)                                                                                     │
     │ - useEffect per lazy load al primo mount                                                                                                                                       │
     │ - Per ogni categoria: Card container con titolo + SimpleGrid responsive di card item                                                                                           │
     │ - Ogni MarketItemCard: nome, simbolo, prezzo formattato locale IT, variazione % colorata                                                                                       │
     │ - Usa formatPct e getVariationColor da formatters.ts (già esistenti)                                                                                                           │
     │ - Loading: spinner + testo; Error: Alert rosso; Simbolo con errore: card con opacity ridotta                                                                                   │
     │                                                                                                                                                                                │
     │ Step 7 — Frontend: Integrazione in Dashboard                                                                                                                                   │
     │                                                                                                                                                                                │
     │ File: src/frontend/valore-frontend/src/pages/Dashboard.page.tsx                                                                                                                │
     │                                                                                                                                                                                │
     │ - Import IconWorld da @tabler/icons-react                                                                                                                                      │
     │ - Import MercatiTab e useMarketData                                                                                                                                            │
     │ - Chiamare const marketData = useMarketData() nel componente                                                                                                                   │
     │ - Aggiungere tab dopo "Analisi":                                                                                                                                               │
     │ <Tabs.Tab value="mercati" leftSection={<IconWorld size={16} />}>Mercati</Tabs.Tab>                                                                                             │
     │ - Aggiungere panel:                                                                                                                                                            │
     │ <Tabs.Panel value="mercati"><MercatiTab marketData={marketData} /></Tabs.Panel>                                                                                                │
     │                                                                                                                                                                                │
     │ ---                                                                                                                                                                            │
     │ Verifica                                                                                                                                                                       │
     │                                                                                                                                                                                │
     │ 1. Endpoint: GET /api/markets/quotes ritorna quote live raggruppate per categoria, senza toccare il DB                                                                         │
     │ 2. Frontend: tab "Mercati" appare nella dashboard dopo "Analisi", lazy-load al click                                                                                           │
     │ 3. UI: 3 sezioni (Indici, Materie Prime, Criptovalute) con griglia di card responsive                                                                                          │
     │ 4. Errori parziali: se un simbolo fallisce, gli altri vengono mostrati normalmente                                                                                             │
     │ 5. TypeScript: npx tsc --noEmit -p tsconfig.app.json — zero errori   