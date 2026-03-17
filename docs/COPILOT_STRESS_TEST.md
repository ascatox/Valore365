# Portfolio Stress Test

## Overview

La funzionalità **Portfolio Stress Test** permette di simulare come un portafoglio di investimento si sarebbe comportato durante crisi finanziarie storiche o scenari ipotetici.

L'obiettivo è aiutare l'utente a capire:

- quanto il portafoglio è resiliente
- quali asset sono più vulnerabili
- quale sarebbe stata la perdita massima
- quanto tempo avrebbe impiegato il portafoglio a recuperare

Questa funzionalità si integra con:

- Portfolio Doctor
- Portfolio Copilot

---

# Obiettivi della funzionalità

La feature deve permettere all'utente di:

- simulare scenari di mercato negativi
- analizzare la perdita massima potenziale
- confrontare il portafoglio con un benchmark
- capire quali asset contribuiscono maggiormente alla perdita

---

# Tipi di stress test

## 1 Historical Stress Test

Simula come il portafoglio si sarebbe comportato durante eventi storici reali.

Scenari iniziali:

| Scenario | Periodo |
|--------|--------|
| Global Financial Crisis | 2008 |
| Dot-Com Crash | 2000–2002 |
| Covid Crash | Feb-Mar 2020 |
| Bear Market | 2022 |

### Output

Per ogni scenario:

- max drawdown
- recovery time
- performance nello scenario
- confronto benchmark

Esempio output
Scenario: Covid Crash

Max Drawdown: -18.4%
Recovery Time: 7 months
Benchmark Drawdown: -21.1%
Risk Level: Medium


---

## 2 Shock Stress Test

Simula shock sintetici applicati alle asset class.

Esempi di shock:

| Scenario | Shock |
|--------|--------|
| Global Equity Crash | -20% |
| US Tech Crash | -30% |
| Bond Selloff | -12% |
| Emerging Markets Crisis | -25% |
| Commodity Drop | -15% |

### Output
Scenario: US Tech Crash

Estimated Portfolio Impact: -9.2%

Most impacted assets:

Nasdaq ETF

MSCI World ETF

Global Equity ETF


---

# Architettura

Pipeline di calcolo:
portfolio positions
↓
price history (yfinance)
↓
portfolio weights
↓
stress engine
↓
stress metrics
↓
Portfolio Copilot explanation


---

# Data Sources

## Price data

Provider principale:
yfinance


Utilizzato per:

- prezzi storici
- calcolo drawdown
- simulazione scenari storici

## ETF Metadata

Provider:


JustETF


Utilizzato per:

- classificazione ETF
- esposizione geografica
- asset class

---

# Stress Engine

Il motore di stress test deve calcolare:

- portfolio returns
- max drawdown
- recovery time
- volatility
- benchmark comparison

---

# Metriche principali

## Max Drawdown

Massima perdita dal picco al minimo.


max_drawdown = (trough - peak) / peak


---

## Recovery Time

Tempo necessario per tornare al valore iniziale.

---

## Portfolio Volatility

Deviazione standard dei rendimenti giornalieri.

---

# API Design

Endpoint suggerito:


GET /api/portfolio/{id}/stress-test


### Response

```json
{
  "scenario": "covid_crash",
  "max_drawdown": -0.184,
  "recovery_months": 7,
  "benchmark_drawdown": -0.211,
  "risk_level": "medium"
}
Backend Tasks

implementare stress engine

scaricare prezzi storici con yfinance

calcolare rendimenti portafoglio

implementare scenari storici

implementare shock sintetici

salvare risultati nel database

Frontend UI

Sezione:

Portfolio → Stress Test

Card per scenario:

Covid Crash

Max Loss: -18%
Recovery: 7 months
Risk Level: Medium

Grafico suggerito:

curva portafoglio nello scenario

confronto benchmark

Integrazione con Copilot

Il Copilot può spiegare il risultato.

Prompt esempio:

Spiega perché il portafoglio perde il 18% nello scenario Covid Crash.
Identifica gli asset che contribuiscono maggiormente alla perdita.

Output esempio:

La perdita principale deriva dall'alta esposizione azionaria globale.
Gli ETF azionari rappresentano oltre il 80% del portafoglio.
Durante il Covid crash i mercati azionari globali hanno perso oltre il 20%.
Estensioni future

Possibili miglioramenti:

Monte Carlo simulation

macroeconomic scenarios

correlation shock

portfolio resilience score

probabilistic stress test

Valore per l'utente

Questa funzionalità aiuta a rispondere a domande fondamentali:

quanto perderebbe il mio portafoglio in una crisi?

il mio portafoglio è troppo rischioso?

quanto tempo servirebbe per recuperare?

Posizionamento prodotto

Questa feature rende Valore365 più simile a:

Portfolio Risk Analyzer

che a un semplice:

Portfolio Tracker