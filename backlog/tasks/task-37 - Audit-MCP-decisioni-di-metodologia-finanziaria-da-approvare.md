---
id: TASK-37
title: 'Audit MCP: decisioni di metodologia finanziaria da approvare'
status: In Progress
assignee: []
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-02T18:37:00Z'
labels:
  - audit-mcp
  - decisione
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raccogliere e approvare le decisioni elencate in backlog/docs/AUDIT_MCP_2026-11_VERIFICA.md (sezione Decisioni): modalità di ribilanciamento, stress senza dati, shock per asset class, tipizzazione degli ETC, fiscalità del reddito, TER mancanti, volatilità canonica, backfill di quote_currency, deduplicazione, aggregato MCP. Bloccante per TASK-38, TASK-39, TASK-40 e in parte per gli altri task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ogni decisione ha l'opzione scelta registrata nel documento di verifica
- [x] #2 I task dipendenti sono aggiornati con la scelta
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approvate il 2026-11-02 le opzioni consigliate (vedi sezione 'Decisioni approvate' in backlog/docs/AUDIT_MCP_2026-11_VERIFICA.md). Restano aperte le decisioni elencate nello stesso documento, da prendere prima dei task corrispondenti.

Nuove decisioni da approvare emerse il 2026-11-02 (giorno 2): (1) valori degli shock gold/commodity/crypto in SHOCK_SCENARIOS, marcati PROVVISORIO in app/constants/stress_scenarios.py; (2) crescita del reddito dai bond indicizzati all'inflazione (ora 0%); (3) l'aliquota fire_capital_gains_tax_rate dell'utente deve continuare a sovrascrivere il 26% nella proiezione del reddito?

Approvate il 2026-11-02 (giorno 3) tutte le decisioni proposte: vedi sezione 'Decisioni approvate (giorno 3)' nel documento di verifica. Restano aperte: backfill quote_currency/FIFO (TASK-41), chiave di deduplicazione (TASK-42), forma dell'aggregato MCP (TASK-43).
<!-- SECTION:NOTES:END -->
