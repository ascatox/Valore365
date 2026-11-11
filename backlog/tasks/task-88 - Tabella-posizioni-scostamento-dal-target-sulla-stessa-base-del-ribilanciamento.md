---
id: TASK-88
title: 'Tabella posizioni: scostamento dal target sulla stessa base del ribilanciamento'
status: To Do
assignee: []
created_date: '2026-11-11T19:00:00Z'
labels:
  - frontend
  - backend
milestone: m-1
dependencies:
  - TASK-85
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Con TASK-85 il proprietario ha deciso un'unica base per i pesi rispetto ai target: il valore degli strumenti con target più la liquidità attuale, la stessa del ribilanciamento. `get_target_drift`, PAC, ribilanciamento e snapshot del Copilot la usano già. Restano due punti sulla base vecchia (peso fra le sole posizioni):

- la colonna dello scostamento nella tabella posizioni (`src/frontend/valore-frontend/src/components/dashboard/holdings/HoldingsTable.tsx`), che lo calcola da sé; oggi il tooltip lo dichiara («liquidità esclusa»), ma l'utente vede un numero diverso da quello del Copilot e del ribilanciamento (es. portafoglio 9101 del seed: AUDTECH.DE 10,0% in linea nella tabella, 9,15% sotto target negli altri tool);
- `calculate_what_if`, il cui `old_drift`/`new_drift` misura la concentrazione sulle sole posizioni.

L'anteprima REST del ribilanciamento (`routes_rebalancing.py`) tiene di proposito i pesi sul solo investito, come documentato in `docs/audit-mcp-2026-11/methodology.md`: valutare se allinearla o lasciarla dichiarata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 La tabella posizioni mostra lo scostamento dal target con lo stesso valore di `get_target_drift` (preferibilmente leggendolo dal backend invece di ricalcolarlo)
- [ ] #2 `calculate_what_if` usa la stessa base per lo scostamento, oppure dichiara nell'output la propria
- [ ] #3 Decisione documentata sull'anteprima REST del ribilanciamento
- [ ] #4 La regola dell'Auditor `B-DRIFT-REBALANCE-WEIGHTS` copre anche il what-if, o una regola nuova lo fa
<!-- AC:END -->
