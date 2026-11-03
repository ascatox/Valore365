---
id: TASK-49
title: 'Liquidità: allineare il summary al modello di liquidità della performance'
status: To Do
assignee: []
created_date: '2026-11-03T11:40:00Z'
labels:
  - backend
  - dati
  - performance
  - decisione
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso in TASK-47 (methodology.md §9.1). summary.cash_balance = cash_balance iniziale + depositi + interessi + dividendi netti − prelievi − commissioni: ignora acquisti e vendite e nessun flusso lo compensa. Diversi punti sommano market_value + cash_balance (hero mobile, totale aggregato, capitale iniziale del Monte Carlo) e il tool di ribilanciamento legge cash_balance come liquidità disponibile. Esempio: deposito 1000, acquisto 8 x 100, vendita 3 x 110, dividendo 20 con 5,20 di ritenuta, prezzo 110 -> totale del summary 1564,80, valore della performance 1094,80 (corretto): differenza = acquisti − vendite = 470. Opzioni: (1) il summary adotta il modello di liquidità della performance (una sola verità, cambia la liquidità mostrata per tutti i portafogli con operazioni); (2) si mantiene il summary e si aggiungono cash_balance_model e total_value (transizione); (3) si riporta la performance alla regola del summary (sconsigliata, reintroduce il bug di TASK-46).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decisione del proprietario registrata (opzione 1, 2 o transizione 2 -> 1)
- [ ] #2 Summary, hero, totale aggregato, Monte Carlo e ribilanciamento usano la liquidità decisa
- [ ] #3 Test con l'esempio sintetico: totale del summary = valore della performance
<!-- AC:END -->
