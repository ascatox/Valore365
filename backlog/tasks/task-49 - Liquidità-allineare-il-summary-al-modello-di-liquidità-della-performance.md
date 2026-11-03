---
id: TASK-49
title: 'Liquidità: allineare il summary al modello di liquidità della performance'
status: Done
assignee: []
created_date: '2026-11-03T11:40:00Z'
updated_date: '2026-11-03T12:52:00Z'
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
- [x] #1 Decisione del proprietario registrata (opzione 1, 2 o transizione 2 -> 1)
- [x] #2 Summary, hero, totale aggregato, Monte Carlo e ribilanciamento usano la liquidità decisa
- [x] #3 Test con l'esempio sintetico: totale del summary = valore della performance
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 decisione del proprietario: opzione 1 (il summary adotta il modello di liquidità della performance, una sola verità).

2026-11-03 implementato (in attesa di verifica sui dati reali prima del rilascio): _cash_balance_detail applica il modello di liquidità della performance; il cash_balance iniziale è liquidità disponibile prima della prima transazione (anche nello storico della performance); nuovi campi implicit_contributions_total, cash_breakdown, cash_model_note. Esempio §9.1: totale del summary da 1564,80 a 1094,80 = valore della performance. Test: test_cash_model_task49.py (11); 858 passed. Rischio: se cash_balance è stato aggiornato a mano per allinearlo al broker, gli acquisti verrebbero sottratti due volte.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Opzione 1 applicata (PR #67): la liquidità di summary, sezione Cash, tool MCP, aggregati, Monte Carlo e ribilanciamento segue il modello di liquidità della performance. Verifica sui dati reali del 2026-11-03: cash_balance iniziale = 0 per i portafogli 19, 24, 26 e 33, quindi nessun rischio di doppia sottrazione; i vecchi valori (175,78 e 819,59) erano depositi − prelievi + dividendi, non saldi del broker. Perché la liquidità coincida con il broker vanno registrati i depositi e i prelievi reali, oppure una rettifica.
<!-- SECTION:FINAL_SUMMARY:END -->
