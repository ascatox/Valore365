---
title: "Copilot Fase 3: potenziamento capacità analitiche e contesto"
status: "Done"
priority: "high"
created: 2026-03-19
labels: ["copilot", "frontend", "backend", "feature", "ai"]
---

# Copilot Fase 3: potenziamento capacità analitiche e contesto

## Contesto

Il Copilot attuale (Fase 2) funziona in modalità agentica con 13 tool e loop di tool-calling (max 3 round). Le risposte sono già buone per domande base (riepilogo, ribilanciamento, what-if), ma mancano capacità analitiche avanzate e contesto intelligente per dare risposte veramente utili su costi, dividendi, esposizione sottostante e stress test.

La codebase ha già le fondamenta: X-Ray ETF (`_xray.py`), stress test (`_stress.py`), weighted TER (`_health.py`), dividend tracking nelle transazioni, Monte Carlo con decumulation. Molti nuovi tool sono wrapper su logica esistente.

Riferimenti principali:
- `src/backend/app/copilot_tools.py` — definizioni e handler dei 13 tool
- `src/backend/app/copilot/streaming.py` — loop agentico (MAX_TOOL_ROUNDS=3)
- `src/backend/app/copilot/snapshot.py` — snapshot per system prompt
- `src/backend/app/prompts/copilot_system_agentic.txt` — system prompt
- `src/backend/app/services/portfolio_doctor/` — health, xray, stress, monte carlo
- `src/frontend/valore-frontend/src/components/copilot/CopilotChat.tsx` — UI chat

## Obiettivo

Potenziare il Copilot su due assi:
1. **Capacità analitiche**: nuovi tool per costi, dividendi, X-Ray, stress test
2. **Intelligenza e contesto**: prompt contestuali per pagina, più round di tool-calling, snapshot arricchito

## Azioni

### 1. Nuovi Tool Analitici

#### T14: `get_dividend_summary`
- Aggrega dividendi ricevuti (transazioni `side='dividend'`)
- Calcola yield atteso del portafoglio (da `asset_metadata.dividend_yield`)
- Proiezione income annuo stimato
- Dati esistenti: transazioni dividend, `dividend_yield/dividend_rate` in metadata, `get_cash_flow_timeline()`

#### T15: `get_cost_breakdown`
- TER per singola posizione (da `etf_enrichment.ter` + `asset_metadata.expense_ratio`)
- TER ponderato totale
- Costo annuo stimato in EUR (TER × market_value)
- Fee drag proiettato a 10 anni
- Dati esistenti: `compute_weighted_ter()`, `get_etf_enrichment_bulk()`, `get_asset_metadata_bulk()`

#### T16: `get_xray_summary`
- Top holdings aggregati sottostanti (wrapper su `compute_portfolio_xray()`)
- Esposizione geografica e settoriale aggregata
- Concentrazione su singoli titoli sottostanti
- Dati esistenti: `compute_portfolio_xray()` già implementato

#### T17: `get_stress_test`
- Impatto di scenari storici (2008, COVID, dot-com, ecc.)
- Drawdown stimato per ogni scenario
- Dati esistenti: `_stress.py` con 20+ scenari

#### T18: `get_income_projection`
- Proiezione dividendi + interessi a 1, 3, 5 anni
- Tax-adjusted con aliquota dell'utente
- Dati parziali: dividend_yield esiste, growth rate va stimato

### 2. Intelligenza e Contesto

#### A2.1: Prompt contestuali per pagina
- Frontend passa `page_context` nel messaggio (es. "dashboard", "portfolio", "doctor", "fire")
- System prompt include suggerimenti mirati per pagina
- Quick prompts diversi per pagina nel frontend (`CopilotChat.tsx`)

#### A2.2: Aumento capacità agentica
- `MAX_TOOL_ROUNDS`: 3 → 5
- `AGENTIC_TIMEOUT_S`: 90 → 120 secondi

#### A2.3: Arricchimento snapshot
- Aggiungere weighted TER al snapshot light
- Aggiungere conteggio posizioni totali
- Aggiungere data ultimo aggiornamento prezzi

### 3. System Prompt Agentico
- Istruzioni per nuovi tool T14-T18
- Regole di correlazione tra dati (es. TER alto + bassa diversificazione)
- Esempi di risposte per scenari comuni

## File da modificare

| File | Modifiche |
|------|-----------|
| `src/backend/app/copilot_tools.py` | Aggiungere T14-T18 (definizioni + handler) |
| `src/backend/app/copilot/streaming.py` | MAX_TOOL_ROUNDS=5, AGENTIC_TIMEOUT_S=120 |
| `src/backend/app/copilot/snapshot.py` | Arricchire snapshot light |
| `src/backend/app/prompts/copilot_system_agentic.txt` | Nuove istruzioni |
| `src/backend/app/api/routes_copilot.py` | Passare page_context |
| `src/frontend/.../copilot/CopilotChat.tsx` | Quick prompts contestuali, page_context |

## Ordine di implementazione suggerito

1. **T16 get_xray_summary** — wrapper su codice esistente, impatto immediato
2. **T17 get_stress_test** — wrapper su codice esistente, impatto immediato
3. **T15 get_cost_breakdown** — dati quasi tutti disponibili
4. **T14 get_dividend_summary** — richiede aggregazione transazioni
5. **A2.2 MAX_TOOL_ROUNDS** — modifica rapida, grande impatto
6. **A2.3 Snapshot arricchito** — modifica rapida
7. **A2.1 Prompt contestuali** — frontend + backend
8. **A3 System prompt** — dopo aver testato i tool
9. **T18 Income projection** — più complesso, ultima priorità

## Verifica

- Testare ogni nuovo tool via `/copilot/chat` con domande mirate
- Verificare che i 13 tool esistenti continuino a funzionare
- Controllare che il modello scelga i tool giusti
- Verificare tempi di risposta con 5 round di tool-calling
- Test end-to-end: domande come "Quanto spendo in commissioni?", "Cosa succede se crolla il mercato?", "Quali sono i miei dividendi attesi?"
