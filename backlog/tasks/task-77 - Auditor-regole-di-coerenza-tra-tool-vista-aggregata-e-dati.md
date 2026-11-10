---
id: TASK-77
title: 'Auditor: regole di coerenza tra tool, vista aggregata e dati'
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

Gruppo D: coerenza tra tool diversi e qualità dei dati. È il gruppo che protegge il Tribunale, perché verifica che lo stesso numero sia uguale ovunque compaia. Copre V365-011 (aggregazioni), V365-009 e V-DUP-IMPORT (import duplicati), V-XLSX-1000 (prezzi per mille), V-QUOTE-CCY-L (quotazioni in pence) e la performance, ricalcolata in modo indipendente con `scripts/audit/twr_mwr_offline_auditor.py`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sono implementate tutte le regole del gruppo D del catalogo
- [ ] #2 Tra le regole: i pesi delle posizioni sommano a cento entro la tolleranza; il valore del riepilogo è uguale alla somma delle posizioni più la liquidità; la vista aggregata coincide con la somma dei singoli portafogli per valore, posizioni e liquidità; le metriche del Doctor coincidono con i valori di X-Ray e health da cui derivano; nessuna coppia di transazioni identiche da import diversi; prezzo × quantità coerente con il controvalore; strumenti quotati a Londra con valuta di quotazione plausibile
- [ ] #3 La regola sulla performance ricalcola TWR e MWR dall'export di audit con la logica dello script offline e confronta con i valori del servizio entro la tolleranza del contratto
- [ ] #4 Le regole vanno in `skip` quando lo scope non lo consente (vista aggregata con un solo portafoglio, nessuna transazione)
- [ ] #5 Ogni regola ha il test che reintroduce il difetto originale e la vede fallire
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/auditor/rules/consistency.py`, `tests/unit/test_auditor_rules_consistency.py`. Se serve importare il ricalcolo da `scripts/audit/twr_mwr_offline_auditor.py`, spostane la logica in una funzione importabile senza cambiarne il comportamento da riga di comando (lo script resta usabile come oggi).
Riferimenti: `services/performance_audit.py`, `get_aggregate_performance_audit`, `services/csv_service.py`, `services/doctor_policy/metrics.py`, `services/tribunal/case_file.py`.
Parallelizzabile con TASK-73, 74, 75, 76, 78.
<!-- SECTION:NOTES:END -->
