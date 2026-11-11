---
id: TASK-75
title: 'Auditor: regole su ribilanciamento, PAC e simulazioni'
status: Done
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

Gruppo B: ribilanciamento, PAC e simulazioni. Coprono V365-003 (i proventi delle vendite non finanziavano gli acquisti e la liquidità usata era contata due volte) e le proprietà di conservazione che ogni simulazione deve rispettare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sono implementate tutte le regole del gruppo B del catalogo
- [x] #2 Tra le regole: nel ribilanciamento la liquidità usata non supera la liquidità disponibile più i proventi delle vendite; la liquidità residua non è negativa; dopo gli ordini lo scostamento dai target non aumenta; con sola nuova liquidità non compaiono vendite; nel calcolo del PAC la somma dei contributi è uguale all'importo indicato
- [x] #3 Le regole usano argomenti fissi e documentati per i tool di simulazione, così l'esito è riproducibile
- [x] #4 Le regole vanno in `skip` quando lo scope non ha target o non ha posizioni
- [x] #5 Ogni regola ha il test che reintroduce il difetto originale e la vede fallire
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/auditor/rules/rebalance_simulation.py`, `tests/unit/test_auditor_rules_rebalance.py`.
Riferimenti: `services/rebalance.py`, `services/pac_service.py`, i tool `calculate_rebalance_orders`, `calculate_what_if`, `calculate_pac_contribution` in `copilot_tools.py`; `services/doctor_policy/scenario.py` per le invarianti di capitale già testate dallo Scenario Lab.
Parallelizzabile con TASK-73, 74, 76, 77, 78.
<!-- SECTION:NOTES:END -->
