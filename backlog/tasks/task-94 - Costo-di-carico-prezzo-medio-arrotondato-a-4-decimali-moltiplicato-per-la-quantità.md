---
id: TASK-94
title: 'Costo di carico: prezzo medio arrotondato a 4 decimali moltiplicato per la quantità'
status: To Do
assignee: []
created_date: '2026-11-16T19:00:00Z'
labels:
  - backend
  - auditor
milestone: m-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso completando TASK-93 (note nelle Deviazioni TASK-93 di `docs/auditor/architecture.md`). Il costo di carico di una posizione viene ricostruito come prezzo medio arrotondato a 4 decimali moltiplicato per la quantità: quando il prezzo medio non è esatto (per esempio 99,01666… con una commissione di 1,00 € su un acquisto) il costo di carico differisce di qualche centesimo dalla somma dei costi effettivi. Sul seed dell'Auditor la regola `D-AGG-SUMS` (P1) falliva di 0,05 € sul portafoglio 9107 finché il seed non è stato modificato per avere un prezzo medio esatto: il difetto resta nel codice e può comparire sui dati reali.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il costo di carico è calcolato dai costi effettivi (somma degli importi e delle commissioni) e il prezzo medio ne è derivato, non il contrario
- [ ] #2 Test unitario con una commissione che rende il prezzo medio periodico; la vista aggregata coincide al centesimo con la somma dei portafogli
- [ ] #3 Il seed dell'Auditor contiene di nuovo un caso con prezzo medio non esatto, e `D-AGG-SUMS` passa
<!-- AC:END -->
