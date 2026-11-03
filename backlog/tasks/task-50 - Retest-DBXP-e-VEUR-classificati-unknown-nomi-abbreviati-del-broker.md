---
id: TASK-50
title: 'Retest: DBXP e VEUR classificati unknown (nomi abbreviati del broker)'
status: In Progress
assignee: []
created_date: '2026-11-03T13:15:00Z'
labels:
  - audit-mcp
  - backend
  - bug
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Retest MCP 2026-11-03, V365-002 parziale. DBXP.DE ('XTR2 EGB13 1CC', ISIN LU0290356871, ~6,39% di Parent) e VEUR ('Azioni Europa') risultano unknown: le regole per nome non riconoscono le abbreviazioni dei broker (EGB = Euro Government Bond) né 'azioni', e l'arricchimento justETF/yFinance per questi ISIN probabilmente manca. In US Tech Crash DBXP riceve lo shock equity (-30%) invece di quello bond. Analisi in backlog/docs/RETEST_MCP_2026-11-03_ANALISI.md §1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Classificazione per ISIN tramite l'arricchimento (justETF), recuperato se mancante, con fonte dichiarata
- [ ] #2 Fallback motivato per nomi abbreviati dei broker (EGB, GOVT, TREAS, azioni, obblig, ...) con test
- [ ] #3 DBXP -> bond e VEUR -> equity in stress, reddito, X-Ray e health (test)
- [ ] #4 Nessuna regressione sulle classificazioni esistenti
<!-- AC:END -->
