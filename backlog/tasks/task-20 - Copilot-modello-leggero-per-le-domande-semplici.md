---
id: TASK-20
title: 'Copilot: modello leggero per le domande semplici'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - backend
  - performance
milestone: m-0
dependencies:
  - TASK-9
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Molte domande al Copilot sono semplici (quanto vale il portafoglio, ultime transazioni) e non richiedono il modello più capace. Indirizzarle a un modello leggero riduce costo e latenza sulla chiave server. Va misurato con la suite di valutazione per non peggiorare le risposte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per ogni provider è configurabile un modello leggero
- [ ] #2 Le domande classificate come semplici usano il modello leggero, le altre il modello principale
- [ ] #3 Se l'utente ha scelto esplicitamente un modello con la propria chiave, quella scelta è sempre rispettata
- [ ] #4 La suite di valutazione mostra che la qualità sulle domande semplici non peggiora oltre una soglia documentata
- [ ] #5 Il modello usato per ogni risposta è registrato nei log
<!-- AC:END -->
