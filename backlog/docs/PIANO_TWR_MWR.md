# Piano: Metriche di Performance — TWR e MWR

## Obiettivo

Aggiungere al portafoglio le metriche **Time-Weighted Return (TWR)** e **Money-Weighted Return (MWR/IRR)** per dare all'utente due prospettive complementari:

- **TWR**: "Quanto ha reso il mercato sui miei asset?" — elimina l'effetto del tempismo dei versamenti.
- **MWR**: "Quanto ho guadagnato io, considerando quando ho versato?" — riflette l'impatto delle decisioni di timing.

---

## Dati già disponibili

| Dato | Tabella/Campo | Note |
|------|---------------|------|
| Transazioni complete | `transactions` (side, trade_at, quantity, price, fees, taxes, trade_currency) | buy, sell, deposit, withdrawal, dividend, fee, interest |
| Prezzi giornalieri | `price_bars_1d` (asset_id, price_date, close, adj_close) | Backfill fino a 365 giorni |
| Tassi FX | `fx_rates_1d` (from_ccy, to_ccy, price_date, rate) | Conversione multi-valuta |
| Cash balance | `portfolios.cash_balance` | Saldo corrente |
| Valuta base | `portfolios.base_currency` | Valuta di riferimento per i calcoli |
| Data creazione | `portfolios.created_at` | Data inception del portafoglio |

---

## Algoritmi

### TWR — Time-Weighted Return

Metodo: **Modified Dietz per sotto-periodi** tra ogni cash flow esterno.

1. Estrarre tutte le transazioni ordinate per `trade_at`
2. Identificare i **cash flow esterni** (deposit, withdrawal) — questi spezzano i sotto-periodi
3. Per ogni sotto-periodo `[t_i, t_{i+1}]`:
   - `V_start` = valore portafoglio a `t_i` (posizioni × close prices + cash)
   - `V_end` = valore portafoglio a `t_{i+1}` (prima del cash flow)
   - `CF` = cash flow esterno a `t_{i+1}`
   - `R_i = (V_end - V_start - CF) / (V_start + CF * weight)` dove weight = proporzione del periodo trascorsa
4. TWR composto: `TWR = Π(1 + R_i) - 1`
5. Annualizzazione: `TWR_ann = (1 + TWR)^(365/giorni) - 1`

**Nota**: buy/sell di asset NON sono cash flow esterni (sono movimenti interni al portafoglio). Solo deposit/withdrawal/dividend cambiano il capitale investito dall'esterno.

### MWR — Money-Weighted Return (IRR)

Metodo: **Internal Rate of Return** con Newton-Raphson.

1. Costruire il vettore dei flussi di cassa:
   - `CF_0` = primo deposito (negativo, è un'uscita per l'investitore)
   - `CF_i` = depositi (negativi) e prelievi (positivi) alle rispettive date
   - `CF_n` = valore finale del portafoglio (positivo) alla data di calcolo
2. Risolvere per `r`: `Σ CF_i / (1 + r)^(t_i / 365) = 0`
3. Implementazione con `scipy.optimize.brentq` con fallback a `newton`
4. Risultato già annualizzato per definizione

---

## Architettura

### Backend

#### 1. Nuovo servizio: `src/backend/app/performance_service.py`

Responsabilità: calcolo TWR e MWR, isolato dalla logica repository.

```python
class PerformanceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    async def calculate_twr(
        self, portfolio_id: int, user_id: str,
        start_date: date | None, end_date: date | None
    ) -> TWRResult

    async def calculate_mwr(
        self, portfolio_id: int, user_id: str,
        start_date: date | None, end_date: date | None
    ) -> MWRResult

    async def get_performance_summary(
        self, portfolio_id: int, user_id: str,
        period: str  # "1m", "3m", "6m", "ytd", "1y", "3y", "all"
    ) -> PerformanceSummary

    async def get_twr_timeseries(
        self, portfolio_id: int, user_id: str,
        start_date: date | None, end_date: date | None
    ) -> list[TWRTimeseriesPoint]
```

**Funzione helper interna** — `_build_portfolio_valuations()`:
- Per ogni data rilevante (cash flow + campionamento giornaliero), calcola il valore totale del portafoglio:
  - Ricostruisce le posizioni (quantità) replay-ando le transazioni
  - Moltiplica per `close` da `price_bars_1d`
  - Converte in `base_currency` via `fx_rates_1d`
  - Somma il cash disponibile a quella data

#### 2. Nuovi modelli: `src/backend/app/models.py`

```python
class TWRResult(BaseModel):
    twr_pct: float              # TWR totale nel periodo (%)
    twr_annualized_pct: float | None  # TWR annualizzato (None se < 1 anno)
    period_days: int
    start_date: str
    end_date: str

class MWRResult(BaseModel):
    mwr_pct: float              # MWR/IRR annualizzato (%)
    period_days: int
    start_date: str
    end_date: str
    converged: bool             # Se il solver ha converguto

class PerformanceSummary(BaseModel):
    period: str
    period_label: str
    start_date: str
    end_date: str
    period_days: int
    twr: TWRResult
    mwr: MWRResult
    total_deposits: float       # Totale versato
    total_withdrawals: float    # Totale prelevato
    net_invested: float         # Netto investito (deposits - withdrawals)
    current_value: float        # Valore attuale portafoglio
    absolute_gain: float        # current_value - net_invested

class TWRTimeseriesPoint(BaseModel):
    date: str
    cumulative_twr_pct: float   # TWR cumulativo fino a quella data
    portfolio_value: float      # Valore portafoglio
```

#### 3. Nuovi metodi repository: `src/backend/app/repository.py`

```python
async def get_transactions_in_range(
    self, portfolio_id: int, user_id: str,
    start_date: date | None, end_date: date | None
) -> list[TransactionRead]

async def get_portfolio_value_at_date(
    self, portfolio_id: int, user_id: str, target_date: date
) -> float
    # Ricostruisce posizioni al target_date e le valuta con close prices

async def get_external_cashflows(
    self, portfolio_id: int, user_id: str,
    start_date: date | None, end_date: date | None
) -> list[CashFlowEntry]
    # Filtra solo deposit/withdrawal/dividend
```

#### 4. Nuovi endpoint: `src/backend/app/main.py`

```
GET /portfolios/{id}/performance/summary?period=1y
    → PerformanceSummary

GET /portfolios/{id}/performance/twr?start_date=&end_date=
    → TWRResult

GET /portfolios/{id}/performance/twr/timeseries?start_date=&end_date=
    → list[TWRTimeseriesPoint]

GET /portfolios/{id}/performance/mwr?start_date=&end_date=
    → MWRResult
```

Parametro `period` accetta: `1m`, `3m`, `6m`, `ytd`, `1y`, `3y`, `all`.
I parametri `start_date` / `end_date` sono alternativi a `period` per date libere.

#### 5. Dipendenze Python

Aggiungere `scipy` per il solver IRR (Newton-Raphson / Brent). Verificare se è già presente, altrimenti:

```
pip install scipy
```

Nessun'altra dipendenza esterna necessaria.

---

### Frontend

#### 6. Nuovo servizio API: `src/frontend/.../services/api.ts`

Aggiungere le funzioni:

```typescript
export interface TWRResult { ... }
export interface MWRResult { ... }
export interface PerformanceSummary { ... }
export interface TWRTimeseriesPoint { ... }

export const getPerformanceSummary = async (
  portfolioId: number, period: string
): Promise<PerformanceSummary> => { ... }

export const getTWRTimeseries = async (
  portfolioId: number, startDate?: string, endDate?: string
): Promise<TWRTimeseriesPoint[]> => { ... }
```

#### 7. Nuovo componente: `src/frontend/.../components/dashboard/analysis/PerformanceMetrics.tsx`

Card con le metriche TWR e MWR affiancate:

```
┌─────────────────────────────────────────────────┐
│  Performance (periodo selezionabile)            │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ TWR      │  │ MWR      │  │ Netto Invest.│  │
│  │ +12.45%  │  │ +9.82%   │  │ € 25.000     │  │
│  │ (ann.)   │  │ (ann.)   │  │              │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Versato  │  │ Prelevato│  │ Guadagno     │  │
│  │ € 30.000 │  │ € 5.000  │  │ +€ 3.200    │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                 │
│  [1M] [3M] [6M] [YTD] [1Y] [3Y] [ALL]         │
└─────────────────────────────────────────────────┘
```

- `SegmentedControl` per il periodo
- 6 KPI cards in `SimpleGrid cols={{ base: 2, md: 3 }}`
- Tooltip su TWR e MWR che spiega la differenza

#### 8. Modifica: `src/frontend/.../components/dashboard/tabs/AnalisiTab.tsx`

Aggiungere `<PerformanceMetrics />` in cima al tab Analisi, sopra i grafici esistenti. Il componente riceve `portfolioId` e carica i dati autonomamente.

---

## Casi limite da gestire

| Caso | Comportamento |
|------|---------------|
| Portafoglio senza transazioni | Ritorna TWR=0, MWR=0 |
| Portafoglio con solo depositi (nessun buy) | TWR=0 (nessun asset da valutare), MWR basato su cash |
| Periodo senza dati di prezzo per un asset | Usa ultimo close disponibile (forward-fill) |
| Asset in valuta diversa da base_currency | Conversione via `fx_rates_1d`, fallback a rate=1 se manca |
| MWR non converge (solver) | `converged: false`, MWR=null nel frontend, mostra "N/D" |
| Valore portafoglio = 0 a inizio periodo | Spostare inizio al primo deposito |
| Dividendi | Trattati come cash flow esterno positivo (aumentano il rendimento TWR) |
| Fee/interest | Fee: riduce il valore; interest: cash flow positivo |

---

## Ordine di implementazione

### Fase 1 — Backend core (priorità alta)

1. **Modelli** (`models.py`): aggiungere `TWRResult`, `MWRResult`, `PerformanceSummary`, `TWRTimeseriesPoint`
2. **Repository** (`repository.py`): aggiungere `get_transactions_in_range`, `get_portfolio_value_at_date`, `get_external_cashflows`
3. **Performance service** (`performance_service.py`): implementare `calculate_twr`, `calculate_mwr`, `get_performance_summary`, `get_twr_timeseries`
4. **Endpoint** (`main.py`): registrare le 4 nuove route

### Fase 2 — Frontend (priorità alta)

5. **API types + functions** (`api.ts`): aggiungere interfacce e funzioni fetch
6. **PerformanceMetrics component**: card con TWR, MWR, periodo selezionabile
7. **Integrazione in AnalisiTab**: montare il componente

### Fase 3 — Qualità

8. **Test unitari** per TWR e MWR con scenari noti (deposito singolo, depositi multipli, prelievi)
9. **Test di integrazione** endpoint → servizio → repository
10. **Verifica TypeScript**: `npx tsc --noEmit`

---

## Stima complessità

| Componente | File | Complessità |
|------------|------|-------------|
| Modelli Pydantic | models.py | Bassa |
| Repository methods | repository.py | Media (query SQL con ricostruzione posizioni) |
| Performance service | performance_service.py (nuovo) | Alta (algoritmi TWR/MWR, gestione edge case) |
| Endpoint API | main.py | Bassa |
| Frontend API | api.ts | Bassa |
| PerformanceMetrics | componente nuovo | Media |
| Integrazione AnalisiTab | AnalisiTab.tsx | Bassa |
| Test | test nuovo | Media |
