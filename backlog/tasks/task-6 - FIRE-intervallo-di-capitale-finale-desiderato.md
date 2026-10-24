---
id: TASK-6
title: 'FIRE: intervallo di capitale finale desiderato'
status: Done
assignee: []
created_date: '2026-10-24 16:50'
updated_date: '2026-10-24 16:50'
labels:
  - backend
  - frontend
  - fire
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nel decumulo FIRE l'utente indica l'intervallo (minimo e massimo, in euro di oggi) entro cui vorrebbe il capitale alla fine dell'orizzonte. La simulazione restituisce la probabilità di finire sotto, dentro o sopra l'intervallo e la fascia di spesa netta sostenibile che lo centra. Salvato nelle impostazioni utente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Minimo e massimo del capitale finale (euro di oggi, indicizzati all'inflazione) come parametri del decumulo, singolo e aggregato
- [x] #2 Probabilità Monte Carlo di finire sotto, dentro e sopra l'intervallo e capitale finale mediano in euro di oggi
- [x] #3 Spesa sostenibile che lascia il minimo (o la soglia, se più alta) e spesa che lascia il massimo
- [x] #4 Parametri persistiti (migrazione DB) e test backend
<!-- AC:END -->
