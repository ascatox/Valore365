# Valore365 — Calcoli Backend

Riferimento completo delle formule e della logica di calcolo usata nel backend per variazioni di portafoglio, rendimenti e proiezioni FIRE.

---

## 1. Variazioni Giornaliere (Day Change)

**File:** `src/backend/app/repository/_summary.py`

### Logica

1. Recupera gli ultimi 2 bar giornalieri per ogni asset dalla tabella `price_bars_1d`
2. Preferisce il campo `previous_close` da `price_ticks` (yFinance) come prezzo di chiusura precedente
3. Fallback: usa il penultimo bar giornaliero da `price_bars_1d`
4. Converte i prezzi in valuta base tramite FX rate (`fx_rates_1d`)

### Formula (livello portafoglio)

```
day_change = Σ (quantity × (current_price_base − previous_price_base))

day_change_pct = (day_change / previous_market_value) × 100
```

dove `previous_market_value = Σ (quantity × previous_price_base)`

### Formula (livello posizione)

**File:** `src/backend/app/repository/_positions.py`

```
pos_day_change_pct = ((current_price_quote / previous_close) − 1) × 100
```

> **Nota:** A livello posizione si usano i prezzi in valuta originale (quote currency, senza FX) per coerenza con il dato yFinance.

---

## 2. P&L Non Realizzato (Unrealized P&L)

**File:** `src/backend/app/repository/_positions.py`

### Per singola posizione

```
cost_basis     = quantity × avg_cost
market_value   = quantity × market_price × fx_rate
unrealized_pl  = market_value − cost_basis
unrealized_pl_pct = (unrealized_pl / cost_basis) × 100    [se cost_basis > 0]
```

### Aggregato portafoglio

**File:** `src/backend/app/repository/_summary.py`

```
market_value   = Σ position.market_value
cost_basis     = Σ (position.quantity × position.avg_cost)
unrealized_pl  = market_value − cost_basis
unrealized_pl_pct = (unrealized_pl / cost_basis) × 100    [se cost_basis > 0]
```

---

## 3. Rendimenti Time-Weighted (TWR)

**File:** `src/backend/app/services/performance_service.py`

Il TWR elimina l'effetto dei flussi di cassa (depositi/prelievi) per misurare la performance pura del portafoglio.

### Logica

1. Divide la timeline in sotto-periodi attorno ad ogni evento di cash flow
2. Per ogni sotto-periodo calcola il rendimento:
   ```
   r_i = (end_value − start_value − cashflow) / start_value
   ```
3. Concatena i rendimenti:
   ```
   linked = Π (1 + r_i)
   twr = linked − 1
   ```
4. Annualizzazione (se periodo ≥ 365 giorni):
   ```
   twr_ann = ((1 + twr) ^ (365 / period_days) − 1) × 100
   ```

### Periodi supportati

| Periodo | Giorni |
|---------|--------|
| 1m      | 30     |
| 3m      | 90     |
| 6m      | 180    |
| 1y      | 365    |
| 3y      | 1095   |

---

## 4. Rendimenti Money-Weighted (MWR / IRR)

**File:** `src/backend/app/services/performance_service.py`

Il MWR riflette l'impatto del timing dei flussi di cassa e corrisponde al tasso interno di rendimento (IRR).

### Formula

Trova il tasso `r` che azzera il valore attuale netto:

```
NPV(r) = Σ (cashflow_i / (1 + r) ^ (days_i / 365)) = 0
```

### Metodi di risoluzione (in ordine di priorità)

1. **Brent's method** (`scipy.optimize.brentq`) — primario
2. **Newton's method** (`scipy.optimize.newton`) — secondario
3. **Bisection con probing** — fallback

Parametri: max 200 iterazioni, tolleranza 1e-9.

---

## 5. Serie Temporale Guadagno/Perdita

**File:** `src/backend/app/services/performance_service.py`

### Formula

```
Per ogni giorno:
  cumulative_invested += depositi − prelievi
  gain = portfolio_value − cumulative_invested
```

> Se non ci sono depositi/prelievi espliciti, usa buy/sell come fallback per il calcolo del capitale investito cumulato.

---

## 6. Serie Temporale Valore Portafoglio

**File:** `src/backend/app/repository/_summary.py`

### Logica

Per ogni giorno dall'inizio alla data corrente:

1. Aggiorna le quantità in base alle transazioni buy/sell del giorno
2. Recupera l'ultimo prezzo disponibile per ogni asset
3. Converte in valuta base tramite FX rate del giorno (o più recente disponibile)
4. Calcola il totale:

```
total_value = Σ (quantity × price × fx_rate)
```

---

## 7. Monte Carlo — Proiezione Portafoglio

**File:** `src/backend/app/services/portfolio_doctor/_monte_carlo.py`

### Costanti

```python
NUM_SIMULATIONS     = 5_000
MAX_PROJECTION_YEARS = 20
PROJECTION_HORIZONS  = [5, 10, 20]   # anni
TRADING_DAYS_YEAR    = 252
```

### Stima parametri di rendimento

**File:** `src/backend/app/services/portfolio_doctor/_holdings.py`

1. Recupera 370 giorni di storico prezzi giornalieri
2. Calcola il valore giornaliero del portafoglio come media pesata:
   ```
   portfolio_value[t] = Σ (weight_i × price_i[t] / price_i[0])
   ```
3. Calcola i log-rendimenti:
   ```
   log_return[t] = ln(portfolio_value[t] / portfolio_value[t−1])
   ```
4. Annualizza:
   ```
   μ_annual = mean(log_returns) × 252
   σ_annual = stdev(log_returns) × √252
   ```

### Simulazione

```
Per ognuna delle 5.000 simulazioni:
  drift = μ_annual − 0.5 × σ_annual²

  Per ogni anno da 1 a 20:
    shock = N(0, 1)     # random gaussiano
    cumulative_log_return += drift + σ_annual × shock
    portfolio_value = 100 × e^(cumulative_log_return)
```

### Output

Percentili (P10, P25, P50, P75, P90) per ogni anno da 0 a 20.

---

## 8. Piano di Decumulo FIRE

**File:** `src/backend/app/services/portfolio_doctor/_monte_carlo.py`

### Input

| Parametro                    | Default        | Descrizione                                      |
|------------------------------|----------------|--------------------------------------------------|
| `initial_capital`            | —              | Valore portafoglio + liquidità                   |
| `annual_withdrawal`          | —              | Prelievo annuale target (EUR)                    |
| `years`                      | —              | Orizzonte temporale (1–80 anni)                  |
| `inflation_rate_pct`         | 2%             | Tasso inflazione annuo                           |
| `other_income_annual`        | 0              | Reddito aggiuntivo (stipendio, pensione)         |
| `capital_gains_tax_rate_pct` | 26%            | Aliquota capital gain (Italia)                   |
| `embedded_gain_ratio_pct`    | calcolato      | (Market Value − Cost Basis) / Market Value × 100 |

### Logica (per ogni simulazione, per ogni anno)

```
1. RENDIMENTO INVESTIMENTO
   annual_return = e^(drift + σ × N(0,1)) − 1      [se σ > 0]
   capital = capital × (1 + annual_return)

2. CALCOLO PRELIEVO
   net_needed = max(0, spending_target − other_income_annual)

3. IMPATTO FISCALE
   embedded_gain_ratio = (capital − cost_basis) / capital
   Risolve: gross_sale − (gross_sale × embedded_gain_ratio × tax_rate) = net_needed
   → gross_sale = net_needed / (1 − embedded_gain_ratio × tax_rate)
   tax = gross_sale × embedded_gain_ratio × tax_rate

4. AGGIORNAMENTO POSIZIONE
   cost_basis −= gross_sale × (cost_basis / capital_before)
   capital −= gross_sale

5. INFLAZIONE
   spending_target ×= (1 + inflation_rate)
```

### Prelievo Sostenibile

Formula basata su rendita reale (annuity approach):

```
real_rate = ((1 + nominal_return) / (1 + inflation)) − 1

Se |real_rate| ≈ 0:
  gross_withdrawal = initial_capital / years
Altrimenti:
  gross_withdrawal = initial_capital × real_rate / (1 − (1 + real_rate)^(−years))

tax_drag = capital_gains_tax × embedded_gain_ratio / 10_000
sustainable_net = gross_withdrawal × (1 − tax_drag) + other_income
```

### Metriche di Output

- `success_rate_pct` — % simulazioni con capitale finale > 0
- `depletion_probability_pct` — % simulazioni con capitale esaurito
- `p25/p50/p75_terminal_value` — Capitale finale ai percentili
- `sustainable_withdrawal` — Prelievo annuale netto raccomandato
- Proiezioni anno per anno con P25/P50/P75

---

## 9. Dividendi e Proiezioni Reddito

**File:** `src/backend/app/copilot_tools.py`

### Riepilogo Dividendi

```
total_dividends     = Σ (qty × price)      per tutte le transazioni dividendo
dividends_last_12m  = Σ                     per transazioni ultimi 365 giorni

Per ogni posizione con dividend_yield:
  weighted_yield += dividend_yield × (position_weight / 100)
  annual_income   = market_value × dividend_yield / 100

projected_annual_income = total_portfolio_mv × weighted_yield / 100
```

### Proiezione Reddito (1, 3, 5 anni)

**Assunzioni:**
- Tasso crescita dividendi: **3% annuo**
- Aliquota fiscale: **26%** (Italia, default)

```
Per ogni orizzonte (1, 3, 5 anni):
  cumulative_income = Σ per y da 1 a years:
    total_annual_dividends × (1 + 0.03)^y

  net_income = cumulative_income × (1 − tax_rate / 100)

yield_on_cost = total_annual_dividends / cost_basis × 100
```

**Output per orizzonte:**
- Reddito lordo/netto cumulato
- Reddito lordo/netto medio annuo
- Yield on cost (%)
- Aliquota fiscale applicata

---

## 10. Fonti Dati

| Tabella          | Contenuto                              |
|------------------|----------------------------------------|
| `price_bars_1d`  | Prezzi giornalieri (OHLCV)             |
| `price_ticks`    | Tick intraday, include `previous_close`|
| `fx_rates_1d`    | Tassi di cambio giornalieri            |
| `transactions`   | Operazioni (buy, sell, dividend, etc.) |

---

## 11. File di Riferimento

| File                                             | Calcoli principali                           |
|--------------------------------------------------|----------------------------------------------|
| `repository/_summary.py`                         | Day change, timeseries, valore intraday      |
| `repository/_positions.py`                       | P&L per posizione, avg cost, day change      |
| `services/performance_service.py`                | TWR, MWR/IRR, gain timeseries                |
| `services/portfolio_doctor/_monte_carlo.py`      | Monte Carlo, decumulo, sostenibilità         |
| `services/portfolio_doctor/_holdings.py`         | Parametri rendimento, volatilità             |
| `copilot_tools.py`                               | Dividend yield, proiezioni reddito           |
