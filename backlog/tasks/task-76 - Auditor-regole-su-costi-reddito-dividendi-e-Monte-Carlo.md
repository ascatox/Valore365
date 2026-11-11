---
id: TASK-76
title: 'Auditor: regole su costi, reddito, dividendi e Monte Carlo'
status: To Do
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - backend
milestone: m-2
dependencies:
  - TASK-72
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Ogni regola segue l'interfaccia di `docs/auditor/architecture.md`: id stabile, titolo in italiano, severità (P0/P1/P2), finding di origine, ambito (portafoglio, vista aggregata, strumento, globale), funzione che riceve il contesto e restituisce esito (`pass`, `fail`, `skip` con motivo) ed evidenza. Le regole leggono i dati solo tramite il contesto, che chiama i tool con `run_tool_sync` del server MCP: così verificano esattamente i numeri che vedono Copilot, Tribunale e Claude.

Per ogni regola un test unitario con un contesto finto dimostra due cose: la regola passa su dati corretti, e fallisce quando si reintroduce il difetto originale (riproducendo l'output sbagliato del finding, o con un monkeypatch del codice corretto). Una regola che non fallisce sul difetto che dichiara di intercettare non è accettata.

Gruppo C: costi, reddito, dividendi, Monte Carlo e variazioni giornaliere. Coprono V-TER-UNIT (TER cento volte più piccolo), V365-007 (costo annuo parziale), V365-004 e V-INCOME-TYPE (reddito tutto in equity), V365-006 (anno 10 mancante nel Monte Carlo), V365-005 e V-DAYMOVERS-ROOT (variazioni giornaliere nulle o finte), V-DIV-MIXED-CCY (somma di valute diverse).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sono implementate tutte le regole del gruppo C del catalogo
- [ ] #2 Tra le regole: il TER di un ETF è nell'intervallo plausibile del contratto e il costo annuo è coerente con TER medio e valore coperto; il reddito di un ETF obbligazionario non è classificato come azionario; il Monte Carlo restituisce esattamente gli anni previsti con percentili ordinati (p25 ≤ p50 ≤ p75, quelli esposti da `get_monte_carlo`); i totali dei dividendi sono separati per valuta; una variazione giornaliera assente non è riportata come zero
- [ ] #3 Le regole vanno in `skip` quando i dati di riferimento mancano (TER non noto, nessun dividendo, mercato chiuso)
- [ ] #4 Ogni regola ha il test che reintroduce il difetto originale e la vede fallire
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/auditor/rules/costs_income.py`, `tests/unit/test_auditor_rules_costs.py`.
Riferimenti: tool `get_cost_breakdown`, `get_income_projection`, `get_dividend_summary`, `get_monte_carlo`, `get_day_movers`; `docs/audit-mcp-2026-11/methodology.md`.
Parallelizzabile con TASK-73, 74, 75, 77, 78.
<!-- SECTION:NOTES:END -->
