---
title: "FIRE 2.0: decumulo con tassazione e modello avanzato"
status: "To Do"
priority: "high"
created: 2026-03-18
labels: ["fire", "frontend", "backend", "feature", "monte-carlo"]
---

# FIRE 2.0: decumulo con tassazione e modello avanzato

## Contesto

La pagina FIRE del progetto oggi copre bene la lettura base di accumulo e decumulo, ma il modello di decumulo non considera la tassazione.
Nel motore backend il `net_withdrawal` viene calcolato sottraendo solo `other_income_annual`, quindi la sostenibilita' del piano risulta ottimistica rispetto a un caso reale.

Riferimenti principali:
- `src/frontend/valore-frontend/src/pages/Fire.page.tsx`
- `src/backend/app/services/portfolio_doctor/_monte_carlo.py`
- `src/backend/app/api/portfolio_health.py`
- `src/frontend/valore-frontend/src/services/api/doctor.ts`
- `src/frontend/valore-frontend/src/services/api/types.ts`

## Obiettivo

Portare la pagina FIRE a una `v2` piu' realistica, introducendo la fiscalita' nel decumulo e preparando il modello per variabili FIRE piu' ricche.

## Scope minimo della v1 di FIRE 2.0

### 1. Tassazione nel decumulo
- Aggiungere un parametro utente per `capital_gains_tax_rate_pct`
- Applicare la tassazione solo alla quota imponibile stimata del prelievo, non all'intero prelievo
- Distinguere chiaramente:
  - `gross_withdrawal`
  - `estimated_taxes`
  - `net_spending_after_tax`
  - `gross_portfolio_withdrawal`
- Ricalcolare la sostenibilita' del piano in base al fabbisogno netto dell'utente e all'impatto lordo sul capitale

### 2. Estensione del modello FIRE
- Preparare il backend per nuove variabili FIRE oltre a:
  - spese annue
  - contributo annuo
  - SWR
  - eta' corrente
  - eta' target
- Valutare struttura persistente piu' flessibile di `user_settings` per evitare proliferazione di colonne
- Opzioni da valutare:
  - tabella dedicata `fire_plans`
  - colonna JSON/JSONB `fire_profile`

### 3. UX pagina FIRE
- Esporre in UI il parametro fiscale del decumulo
- Aggiornare card metriche, tabella timeline e testo interpretativo
- Rendere esplicita la differenza tra:
  - spesa desiderata netta
  - prelievo lordo richiesto
  - tasse stimate
  - capitale residuo

## Approccio tecnico proposto

### Backend
- Estendere gli endpoint:
  - `GET /portfolios/{portfolio_id}/decumulation`
  - `GET /portfolios/aggregate/decumulation`
- Nuovi parametri query:
  - `capital_gains_tax_rate_pct`
  - eventuale `embedded_gain_ratio` oppure stima derivata da `market_value` e `cost_basis`
- Aggiornare il motore Monte Carlo di decumulo per:
  - stimare la quota imponibile del prelievo
  - calcolare le tasse annue
  - sottrarre dal capitale il prelievo lordo necessario, non solo il netto desiderato
- Estendere gli schemi response con campi fiscali dedicati

### Frontend
- Aggiornare il pannello input della pagina FIRE con il nuovo campo fiscale
- Propagare il nuovo parametro nelle chiamate API del decumulo
- Aggiornare i tipi TS delle response
- Mostrare la fiscalita' nella timeline di decumulo e nella sintesi del piano

## Formula iniziale consigliata

Per una prima implementazione pragmatica:

- `embedded_gain_ratio = max(0, market_value - cost_basis) / market_value`
- `taxable_amount = gross_sale * embedded_gain_ratio`
- `estimated_taxes = taxable_amount * tax_rate`
- `net_spending_after_tax = gross_sale - estimated_taxes + other_income`

Nota:
- questa e' una stima aggregata coerente per una `v1`
- in una fase successiva si puo' migliorare il modello con lotti fiscali, differenze tra strumenti e regimi nazionali

## File coinvolti

- `src/backend/app/api/portfolio_health.py`
- `src/backend/app/schemas/portfolio_doctor.py`
- `src/backend/app/services/portfolio_doctor/_monte_carlo.py`
- `src/frontend/valore-frontend/src/pages/Fire.page.tsx`
- `src/frontend/valore-frontend/src/services/api/doctor.ts`
- `src/frontend/valore-frontend/src/services/api/types.ts`
- eventuali modelli/settings FIRE in:
  - `src/backend/app/models.py`
  - repository/migrazioni database

## Criteri di accettazione

- [ ] Il decumulo accetta un parametro fiscale esplicito per la tassazione delle plusvalenze
- [ ] Le proiezioni annuali espongono tasse stimate, prelievo lordo e netto post-imposte
- [ ] `sustainable_withdrawal` e `success_rate_pct` riflettono la fiscalita'
- [ ] La UI FIRE mostra in modo chiaro l'impatto fiscale del decumulo
- [ ] Il flusso funziona sia in modalita' singola sia aggregata
- [ ] Il modello e' predisposto all'aggiunta di nuove variabili FIRE senza accoppiare tutto a `user_settings`

## Ordine di implementazione consigliato

1. Estendere API e schemi di decumulo con tassazione
2. Aggiornare il motore Monte Carlo backend
3. Aggiornare i tipi e il client API frontend
4. Integrare il nuovo input fiscale nella pagina FIRE
5. Rifinire testi, metriche e timeline
