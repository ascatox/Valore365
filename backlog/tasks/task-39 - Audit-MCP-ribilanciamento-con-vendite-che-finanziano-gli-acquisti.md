---
id: TASK-39
title: 'Audit MCP: ribilanciamento con vendite che finanziano gli acquisti'
status: In Progress
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-02T20:09:00Z'
labels:
  - audit-mcp
  - mcp
  - backend
  - bug
milestone: m-1
dependencies:
  - TASK-37
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-003. _calculate_rebalance_orders non usa i proventi delle vendite, calcola la vendita come drift% del valore della posizione invece del totale e conta due volte la liquidità in cash_used. Estrarre l'algoritmo di routes_rebalancing.rebalance_preview in un servizio (services/rebalance.py) usato sia dal route sia dal tool, con le modalità buy_only/rebalance/sell_only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il route e il tool usano lo stesso servizio
- [x] #2 Senza flussi esterni il capitale è conservato: cash_after = cash_before + external + sells - buys - fees >= 0
- [x] #3 Dopo il piano i pesi sono più vicini ai target
- [x] #4 Il risultato non dipende dall'ordine di iterazione dei target
- [x] #5 Test con cash=0, cash>0, target incompleti, singolo strumento e 0 posizioni
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementato services/rebalance.py usato da route e tool. In attesa di conferma: la banda di 0,5 pp è usata come soglia di attivazione (se una posizione supera la banda, tutte tornano al target). Il route mantiene la semantica precedente (pesi sul solo investito, nessuna banda). Test: tests/unit/test_rebalance_plan.py.
<!-- SECTION:NOTES:END -->
