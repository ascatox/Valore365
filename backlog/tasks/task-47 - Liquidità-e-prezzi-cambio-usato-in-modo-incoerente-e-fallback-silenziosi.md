---
id: TASK-47
title: 'Liquidità e prezzi: cambio usato in modo incoerente e fallback silenziosi'
status: To Do
assignee: []
created_date: '2026-11-03T10:53:00Z'
labels:
  - audit-mcp
  - backend
  - dati
milestone: m-1
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso in TASK-44 (controlli C2 e C4). get_cash_balance converte con il cambio più recente (_utilities.py ~307), mentre il summary usa quello della data dell'operazione; un cambio mancante diventa 1.0 senza avviso. Senza cambio per la valuta di quotazione, il prezzo di una posizione ripiega in silenzio sul costo medio (_positions.py ~387-396). Le ritenute sui dividendi (taxes) sono ignorate nel saldo di liquidità.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Stesso criterio di cambio fra get_cash_balance e summary, documentato
- [ ] #2 Cambio mancante e prezzo ripiegato sul costo segnalati nell'output (flag), non nascosti
- [ ] #3 Decisione sulle ritenute dei dividendi documentata e testata
<!-- AC:END -->
