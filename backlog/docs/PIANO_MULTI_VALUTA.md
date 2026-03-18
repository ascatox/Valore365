# Piano Evolutivo: Sistema Multi-Valuta

> **Stato**: Pianificazione
> **Data**: 2026-03-08
> **Priorita**: Alta
> **Stima complessita**: L (Large) — coinvolge DB, backend, frontend, data pipeline

---

## 1. Analisi dello Stato Attuale

### 1.1 Cosa funziona gia

Il sistema ha **basi solide** per il multi-valuta:

| Componente | Stato attuale |
|---|---|
| `portfolios.base_currency` | Presente (char(3)), ogni portafoglio ha la sua valuta base |
| `assets.quote_currency` | Presente — ogni asset ha la valuta di quotazione |
| `transactions.trade_currency` | Presente — ogni transazione registra la valuta di esecuzione |
| `fx_rates_1d` | Tabella esistente con tassi giornalieri (from_ccy, to_ccy, rate) |
| `HistoricalIngestionService` | Scarica automaticamente i tassi FX necessari durante il backfill |
| `formatMoney()` (frontend) | Accetta gia un parametro `currency` (default `'EUR'`) |

### 1.2 Limitazioni Attuali

| Area | Problema |
|---|---|
| **FX nelle posizioni** | `get_portfolio_positions()` converte in base_currency usando `fx_rate_on_or_before()`, ma non espone il tasso FX usato ne il valore nella valuta originale |
| **Frontend hardcoded EUR** | `formatMoney()` ha default `'EUR'`; molti componenti non passano la valuta del portafoglio |
| **Locale `it-IT` fisso** | `Intl.NumberFormat('it-IT', ...)` e hardcoded — un utente USD vede "$ 1.234,56" con virgola decimale italiana |
| **Nessun FX real-time** | I tassi FX vengono aggiornati solo nel backfill giornaliero, non durante il price refresh live |
| **Mancanza tasso nella transazione** | La transazione registra `trade_currency` ma non il `fx_rate_at_trade` — il tasso viene ricostruito dopo |
| **Cash multi-valuta parziale** | `CashBalanceResponse.currency_breakdown` esiste ma il `total_cash` e calcolato senza conversione FX esplicita |
| **Nessun gain/loss FX** | Non c'e separazione tra guadagno da prezzo e guadagno/perdita da cambio |
| **Settings utente senza valuta** | `app_user_settings` non ha una `display_currency` per l'utente |
| **FIRE page** | Tutte le cifre FIRE (spese annuali, contributi) non hanno valuta associata |
| **Report CSV export** | Non include info valuta nelle esportazioni |

---

## 2. Architettura Target

```
                    +-----------------------+
                    |    User Settings      |
                    |  display_currency: EUR |
                    |  display_locale: it-IT|
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    |   Frontend Layer       |
                    |  CurrencyContext       |
                    |  useFormatMoney()      |
                    |  useFxRates()          |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    |   API Layer            |
                    |  Tutti gli importi     |
                    |  restituiti con:       |
                    |  - value_base_ccy      |
                    |  - value_original_ccy  |
                    |  - fx_rate_used        |
                    +-----------+-----------+
                                |
          +---------------------+---------------------+
          |                                           |
+---------v---------+                     +-----------v-----------+
|  FX Rate Service  |                     |  Portfolio Engine      |
|  - Real-time FX   |                     |  - Gain separazione:  |
|  - Cache 5min     |                     |    price vs FX        |
|  - Fallback 1d    |                     |  - TWR/MWR FX-aware  |
+-------------------+                     +------------------------+
```

---

## 3. Fasi di Implementazione

### FASE 1 — Fondamenta Backend (Settimane 1-2)

#### 1.1 Nuovo servizio FX centralizzato

Creare `src/backend/app/fx_service.py`:

```python
class FxService:
    """Servizio centralizzato per conversioni valutarie."""

    def get_rate(self, from_ccy: str, to_ccy: str, on_date: date | None = None) -> float:
        """Ritorna il tasso di cambio. 1.0 se stessa valuta."""

    def get_rate_realtime(self, from_ccy: str, to_ccy: str) -> FxQuote:
        """Tasso real-time con cache TTL 5min."""

    def convert(self, amount: float, from_ccy: str, to_ccy: str, on_date: date | None = None) -> float:
        """Converte un importo tra valute."""

    def get_rates_bulk(self, pairs: list[tuple[str,str]], on_date: date) -> dict[tuple[str,str], float]:
        """Batch lookup per evitare N+1 queries."""
```

**Razionale**: Oggi la logica `fx_rate_on_or_before()` e duplicata 5+ volte in `repository.py` (linee 1386, 1508, 1743, 1925, 2049). Un servizio unico elimina la duplicazione e aggiunge caching.

#### 1.2 Migrazione DB: `fx_rate_at_trade` su transazioni

```sql
-- migration: 20260310_01_tx_fx_rate_at_trade
ALTER TABLE transactions
  ADD COLUMN fx_rate_at_trade numeric(28,10);

-- Backfill dai tassi storici
UPDATE transactions t
SET fx_rate_at_trade = COALESCE(
  (SELECT rate FROM fx_rates_1d
   WHERE from_ccy = t.trade_currency
   AND to_ccy = (SELECT base_currency FROM portfolios WHERE id = t.portfolio_id)
   AND price_date <= t.trade_at::date
   ORDER BY price_date DESC LIMIT 1),
  1.0
)
WHERE t.trade_currency != (SELECT base_currency FROM portfolios WHERE id = t.portfolio_id);

UPDATE transactions t
SET fx_rate_at_trade = 1.0
WHERE fx_rate_at_trade IS NULL;
```

#### 1.3 Migrazione DB: `display_currency` nelle impostazioni utente

```sql
-- migration: 20260310_02_user_display_currency
ALTER TABLE app_user_settings
  ADD COLUMN display_currency char(3) NOT NULL DEFAULT 'EUR',
  ADD COLUMN display_locale varchar(10) NOT NULL DEFAULT 'it-IT';
```

#### 1.4 Aggiornare modelli Pydantic

```python
# models.py - aggiornamenti
class UserSettingsRead(BaseModel):
    ...
    display_currency: str = "EUR"
    display_locale: str = "it-IT"

class Position(BaseModel):
    ...
    market_value_original: float       # valore nella quote_currency
    market_value_base: float           # valore nella base_currency del portafoglio
    fx_rate: float                     # tasso usato
    quote_currency: str                # valuta di quotazione dell'asset

class TransactionRead(TransactionCreate):
    id: int
    fx_rate_at_trade: float | None = None
```

**File coinvolti**:
- `src/backend/app/fx_service.py` (nuovo)
- `src/backend/app/models.py`
- `src/backend/app/repository.py` (refactor fx_rate_on_or_before)
- `database/migrations/20260310_01_tx_fx_rate_at_trade.sql` (nuovo)
- `database/migrations/20260310_02_user_display_currency.sql` (nuovo)

---

### FASE 2 — Posizioni e Summary Multi-Valuta (Settimane 2-3)

#### 2.1 Arricchire la risposta Position

Modificare `get_portfolio_positions()` in `repository.py` per restituire:

| Campo | Descrizione |
|---|---|
| `quote_currency` | Valuta di quotazione dell'asset (da `assets.quote_currency`) |
| `market_price_original` | Prezzo nella valuta originale |
| `market_value_original` | qty * price nella valuta originale |
| `market_value_base` | Valore convertito nella `base_currency` del portafoglio |
| `fx_rate` | Tasso di cambio utilizzato |
| `fx_impact_pct` | Percentuale di impatto cambio sul P&L |

#### 2.2 Separazione P&L: prezzo vs cambio

Per ogni posizione calcolare:
- **Price P&L**: variazione dovuta al movimento di prezzo (in valuta originale, poi convertita)
- **FX P&L**: variazione dovuta al movimento del tasso di cambio
- **Total P&L**: somma dei due

```python
# Esempio calcolo
price_pl = (current_price - avg_cost_original) * quantity  # in quote_currency
fx_pl = market_value_original * (current_fx - avg_fx) / avg_fx  # impatto cambio
total_pl = price_pl * current_fx + fx_pl  # in base_currency
```

#### 2.3 PortfolioSummary arricchito

```python
class PortfolioSummary(BaseModel):
    ...
    fx_impact: float = 0.0           # guadagno/perdita da cambio totale
    fx_impact_pct: float = 0.0
    currency_exposure: list[CurrencyExposureItem] = []  # esposizione per valuta

class CurrencyExposureItem(BaseModel):
    currency: str
    market_value: float
    weight_pct: float
    fx_rate: float
```

**File coinvolti**:
- `src/backend/app/repository.py` (get_portfolio_positions, get_portfolio_summary)
- `src/backend/app/models.py` (Position, PortfolioSummary)
- `src/backend/app/main.py` (endpoint /positions, /summary)

---

### FASE 3 — FX Real-Time e Price Refresh (Settimana 3)

#### 3.1 FX nel price refresh

Estendere `PriceIngestionService.refresh_prices()` per aggiornare anche i tassi FX live:

```python
# In pricing_service.py
def refresh_prices(self, ...):
    # ... codice esistente per prezzi asset ...

    # Nuovo: refresh FX pairs necessarie
    fx_pairs_needed = self._get_needed_fx_pairs(portfolio_id, user_id)
    for from_ccy, to_ccy in fx_pairs_needed:
        fx_quote = client.get_fx_quote(from_ccy, to_ccy)
        self.repository.save_fx_tick(from_ccy, to_ccy, fx_quote.rate, fx_quote.ts)
```

#### 3.2 Cache FX in-memory

```python
# fx_service.py
class FxRateCache:
    """Cache con TTL 5 minuti per tassi FX real-time."""
    _cache: dict[str, tuple[float, datetime]]  # key -> (rate, fetched_at)
    TTL = timedelta(minutes=5)
```

#### 3.3 Nuova tabella `fx_ticks` per tassi intraday

```sql
-- migration: 20260315_01_fx_ticks
CREATE TABLE fx_ticks (
  from_ccy char(3) NOT NULL,
  to_ccy char(3) NOT NULL,
  provider text NOT NULL,
  ts timestamptz NOT NULL,
  rate numeric(28,10) NOT NULL CHECK (rate > 0),
  PRIMARY KEY (from_ccy, to_ccy, provider, ts)
);
CREATE INDEX idx_fx_ticks_pair_ts ON fx_ticks(from_ccy, to_ccy, ts DESC);
```

**File coinvolti**:
- `src/backend/app/fx_service.py` (cache)
- `src/backend/app/pricing_service.py` (FX refresh)
- `src/backend/app/finance_client.py` (get_fx_quote se non presente)
- `database/migrations/20260315_01_fx_ticks.sql` (nuovo)

---

### FASE 4 — Frontend Multi-Valuta (Settimane 3-4)

#### 4.1 CurrencyContext React

```typescript
// src/contexts/CurrencyContext.tsx
interface CurrencyContextValue {
  baseCurrency: string;          // dal portafoglio attivo
  displayCurrency: string;       // dalle settings utente
  locale: string;                // 'it-IT', 'en-US', etc.
  formatMoney: (value: number, currency?: string) => string;
  formatMoneyWithSign: (value: number, currency?: string) => string;
}
```

#### 4.2 Refactor `formatMoney` e `formatters.ts`

Rimuovere il default hardcoded `'EUR'` e derivare la valuta dal contesto:

```typescript
// Prima (attuale)
export const formatMoney = (value: number, currency = 'EUR', ...) => { ... }

// Dopo
export const formatMoney = (value: number, currency: string, locale: string, ...) => { ... }
```

#### 4.3 Componenti da aggiornare

| Componente | Cambiamento |
|---|---|
| `KpiStatsGrid.tsx` | Usare `baseCurrency` dal summary |
| `KpiStatCard.tsx` | Passare valuta dal parent |
| `HoldingsTable.tsx` | Mostrare colonna valuta originale + valore convertito |
| `PosizioniTab.tsx` | Aggiungere colonna FX rate e P&L FX |
| `PerformanceMetrics.tsx` | Valori monetari con valuta corretta |
| `PanoramicaTab.tsx` | Summary con valuta portafoglio |
| `AnalisiTab.tsx` | Grafici con valuta |
| `BestWorstCards.tsx` | Formattazione valuta |
| `AllocationDoughnut.tsx` | Tooltip con valuta |
| `TransactionsSection.tsx` | Colonna fx_rate, valuta |
| `CashSection.tsx` | Currency breakdown gia presente, mostrare meglio |
| `Fire.page.tsx` | Valuta per FIRE parameters |
| `Settings.page.tsx` | Selettore display_currency + locale |
| `DashboardMobileHeader.tsx` | Simbolo valuta |
| `DashboardMobileKpiCarousel.tsx` | Valuta nei KPI |
| `MobileHoldingsCards.tsx` | Valuta nelle card |
| `MonteCarloCard.tsx` | Proiezioni con valuta |

#### 4.4 Selettore valuta nelle Settings

Aggiungere alla pagina Settings:
- **Valuta di visualizzazione**: dropdown con EUR, USD, GBP, CHF, JPY, ...
- **Formato numerico**: dropdown con locales (Italiano, English US, English UK, Deutsch, ...)

**File coinvolti**:
- `src/frontend/valore-frontend/src/contexts/CurrencyContext.tsx` (nuovo)
- `src/frontend/valore-frontend/src/components/dashboard/formatters.ts`
- Tutti i 17 componenti elencati sopra
- `src/frontend/valore-frontend/src/services/api.ts` (tipi aggiornati)

---

### FASE 5 — Performance Multi-Valuta (Settimana 4-5)

#### 5.1 TWR/MWR con consapevolezza FX

I calcoli TWR e MWR devono convertire tutti i flussi di cassa nella `base_currency` del portafoglio usando il tasso FX del giorno:

```python
# performance_service.py
def calculate_twr(self, ...):
    # Ogni sub-period value deve essere in base_currency
    # I cashflows devono essere convertiti al tasso FX del giorno
    for cf in cashflows:
        fx = self.fx_service.get_rate(cf.currency, base_ccy, cf.date)
        cf_amount_base = cf.amount * fx
```

#### 5.2 Timeseries con doppia valuta

Le timeseries di performance possono opzionalmente ritornare valori in base_currency e display_currency:

```python
class TWRTimeseriesPoint(BaseModel):
    date: str
    cumulative_twr_pct: float
    portfolio_value: float
    portfolio_value_display_ccy: float | None = None  # se display != base
```

#### 5.3 Attribution FX nel periodo

```python
class PerformanceSummary(BaseModel):
    ...
    fx_attribution_pct: float = 0.0   # quanto del rendimento e dovuto a FX
    price_attribution_pct: float = 0.0 # quanto e dovuto a prezzo
```

**File coinvolti**:
- `src/backend/app/performance_service.py`
- `src/backend/app/models.py`
- `src/backend/app/fx_service.py`

---

### FASE 6 — Funzionalita Avanzate (Settimane 5-6)

#### 6.1 Widget Esposizione Valutaria nella Dashboard

Nuovo componente `CurrencyExposureChart.tsx`:
- Grafico a ciambella con esposizione per valuta
- Dettaglio hover: valore per valuta, peso %, tasso attuale

#### 6.2 Grafico storico tassi FX

Componente `FxRateChart.tsx`:
- Visualizzazione storica dei tassi per le coppie rilevanti al portafoglio
- Utile per capire l'impatto FX nel tempo

#### 6.3 CSV Import con FX

Estendere il CSV import per gestire:
- Colonna `fx_rate` opzionale nel CSV
- Se assente, recuperare il tasso storico automaticamente
- Validazione della coerenza valuta

#### 6.4 Rebalance FX-aware

Il motore di rebalancing deve considerare:
- Costo implicito di conversione valutaria
- Preferenza per asset nella stessa valuta (opzionale)
- Calcolo del drift in base_currency

#### 6.5 PAC Multi-Valuta

Estendere PAC rules:
- Campo `currency` nella regola PAC
- Conversione automatica se `mode='amount'` e valuta diversa da quote_currency

#### 6.6 Copilot FX-aware

Arricchire il contesto del Copilot con:
- Esposizione valutaria del portafoglio
- Impatto FX sulle performance
- Suggerimenti su copertura cambio (hedging)

**File coinvolti** (nuovi):
- `src/frontend/valore-frontend/src/components/dashboard/currency/CurrencyExposureChart.tsx`
- `src/frontend/valore-frontend/src/components/dashboard/currency/FxRateChart.tsx`

---

## 4. Dettaglio Migrazioni Database

| # | Migrazione | Tipo | Rischio |
|---|---|---|---|
| 1 | `20260310_01_tx_fx_rate_at_trade` | ALTER + UPDATE | Basso — colonna nullable, backfill safe |
| 2 | `20260310_02_user_display_currency` | ALTER | Basso — colonne con default |
| 3 | `20260315_01_fx_ticks` | CREATE TABLE | Nessuno — nuova tabella |
| 4 | `20260320_01_position_fx_snapshot` | CREATE TABLE (opzionale) | Basso |

Tutte le migrazioni sono **retrocompatibili** — nessuna colonna rimossa, solo aggiunte.

---

## 5. API Nuove / Modificate

### Nuovi Endpoint

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/fx/rates?pairs=EUR/USD,EUR/GBP` | Tassi FX correnti |
| GET | `/fx/rates/history?pair=EUR/USD&days=30` | Storico tassi |
| GET | `/portfolios/{id}/currency-exposure` | Esposizione valutaria |

### Endpoint Modificati (backward-compatible)

| Endpoint | Cambiamento |
|---|---|
| `GET /portfolios/{id}/positions` | Nuovi campi opzionali: `quote_currency`, `fx_rate`, `market_value_original` |
| `GET /portfolios/{id}/summary` | Nuovi campi: `fx_impact`, `currency_exposure` |
| `GET /portfolios/{id}/performance/summary` | Nuovo campo: `fx_attribution_pct` |
| `GET /settings/user` | Nuovi campi: `display_currency`, `display_locale` |
| `PUT /settings/user` | Accetta: `display_currency`, `display_locale` |
| `POST /transactions` | Nuovo campo opzionale: `fx_rate_at_trade` |

---

## 6. Test Plan

### Unit Test

| Area | Copertura |
|---|---|
| `FxService` | get_rate, convert, cache TTL, fallback, same-currency=1.0 |
| `FxService.get_rates_bulk` | Batch lookup, cache hit/miss |
| Position P&L split | price_pl + fx_pl = total_pl |
| TWR con FX | Cashflow in valute diverse |
| MWR con FX | IRR con flussi multi-valuta |

### Integration Test

| Scenario | Descrizione |
|---|---|
| Portafoglio EUR con asset USD | Verifica conversione posizioni e summary |
| Portafoglio USD con asset EUR+JPY | Multi-valuta misto |
| Transazione con fx_rate_at_trade | Verifica persistenza e utilizzo |
| Price refresh + FX refresh | Entrambi aggiornati |
| Cambio display_currency | Settings persiste e UI aggiorna |

### E2E / Manuale

- [ ] Creare portafoglio EUR, aggiungere AAPL (USD), verificare conversione
- [ ] Cambiare display_currency da EUR a USD, verificare tutta la UI
- [ ] CSV import con asset multi-valuta
- [ ] FIRE page con valuta corretta
- [ ] Mobile responsive con simboli valuta

---

## 7. Rischi e Mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| **Tassi FX mancanti** per coppie esotiche | Valori errati | Fallback a tasso 1.0 + warning visibile; triangolazione via USD |
| **Performance degradata** per N+1 query FX | Lentezza API | Batch lookup + cache in-memory con TTL |
| **Breaking change API** | Client rotti | Tutti i nuovi campi sono opzionali; nessun campo rimosso |
| **Precisione numerica** | Errori di arrotondamento | Usare `numeric(28,10)` in DB; `Decimal` in Python per calcoli critici |
| **Complessita TWR/MWR** | Calcoli errati | Test approfonditi con scenari noti; confronto con tool esterni |
| **Provider FX rate limits** | Backfill falliti | Cache aggressiva; fallback a ultimo tasso noto |

---

## 8. Ordine di Priorita Consigliato

```
Fase 1 (Fondamenta)     ████████████░░░░░░░░░░  Settimane 1-2
Fase 2 (Posizioni)       ░░░░████████░░░░░░░░░░  Settimane 2-3
Fase 4 (Frontend base)   ░░░░░░██████████░░░░░░  Settimane 3-4
Fase 3 (FX real-time)    ░░░░░░░░████████░░░░░░  Settimana 3
Fase 5 (Performance)     ░░░░░░░░░░░░████████░░  Settimane 4-5
Fase 6 (Avanzate)        ░░░░░░░░░░░░░░░░██████  Settimane 5-6
```

Le Fasi 1 e 2 sono **bloccanti** per tutto il resto. La Fase 4 (frontend) puo iniziare in parallelo con la Fase 3.

---

## 9. Valute Supportate (Fase Iniziale)

| Codice | Nome | Priorita |
|---|---|---|
| EUR | Euro | P0 (default) |
| USD | Dollaro USA | P0 |
| GBP | Sterlina britannica | P0 |
| CHF | Franco svizzero | P1 |
| JPY | Yen giapponese | P1 |
| CAD | Dollaro canadese | P2 |
| AUD | Dollaro australiano | P2 |
| SEK | Corona svedese | P2 |
| NOK | Corona norvegese | P2 |
| DKK | Corona danese | P2 |

Il sistema non limita le valute a questa lista — qualsiasi codice ISO 4217 e accettato. Questa lista indica solo le valute testate e con formattazione verificata.

---

## 10. Glossario

| Termine | Definizione |
|---|---|
| **base_currency** | Valuta del portafoglio in cui vengono consolidati tutti i valori |
| **quote_currency** | Valuta in cui un asset e quotato sul mercato |
| **trade_currency** | Valuta in cui e stata eseguita una transazione |
| **display_currency** | Valuta scelta dall'utente per la visualizzazione (puo differire da base) |
| **fx_rate** | Tasso di cambio `from_ccy/to_ccy` (1 EUR = 1.08 USD -> rate = 1.08) |
| **Price P&L** | Profitto/perdita dovuto alla variazione del prezzo dell'asset |
| **FX P&L** | Profitto/perdita dovuto alla variazione del tasso di cambio |
