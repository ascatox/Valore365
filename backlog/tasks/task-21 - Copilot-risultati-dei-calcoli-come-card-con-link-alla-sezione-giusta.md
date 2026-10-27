---
id: TASK-21
title: 'Copilot: risultati dei calcoli come card con link alla sezione giusta'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - frontend
  - backend
milestone: m-0
dependencies: []
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quando il Copilot calcola ordini di ribilanciamento, un piano PAC o una simulazione what-if, il risultato arriva solo come testo e l'utente deve trovare da solo la pagina dove agire. Mostrare il risultato del tool come card strutturata, con un link alla sezione giusta, rende la risposta più usabile. Il Copilot resta in sola lettura: la card porta alla pagina, non esegue operazioni.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Quando la risposta usa `calculate_rebalance_orders`, `calculate_pac_contribution` o `calculate_what_if`, il frontend mostra una card con i dati del tool
- [ ] #2 La card ha un link alla sezione dell'app dove l'utente può agire
- [ ] #3 Nessuna card scrive dati o esegue operazioni
- [ ] #4 I dati della card arrivano dall'output del tool, non dal testo generato
- [ ] #5 La card funziona su mobile e desktop
<!-- AC:END -->
