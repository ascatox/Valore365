---
id: TASK-5
title: 'FIRE: capitale minimo, pensione, spese una tantum e crescita contributo'
status: Done
assignee: []
created_date: '2026-10-23 14:25'
updated_date: '2026-10-23 14:25'
labels:
  - backend
  - frontend
  - fire
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nuovi parametri nel pianificatore FIRE (accumulo e decumulo): capitale minimo da preservare (euro di oggi, indicizzato), pensione annua con età di inizio, spese una tantum per età, crescita annua del contributo. Salvati nelle impostazioni utente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Soglia di capitale nel target FIRE e nella simulazione di decumulo (probabilità e anno di sforamento, spesa sostenibile che preserva la soglia)
- [x] #2 Pensione e spese una tantum in accumulo e decumulo
- [x] #3 Crescita del contributo in anni stimati e contributo richiesto
- [x] #4 Parametri persistiti (migrazione DB) e test backend/frontend
<!-- AC:END -->
