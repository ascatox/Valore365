---
id: TASK-46
title: >-
  Performance: con depositi nel periodo gli acquisti vengono contati come
  rendimento (TWR)
status: In Progress
assignee: []
created_date: '2026-11-03T10:53:00Z'
updated_date: '2026-11-03T11:00:00Z'
labels:
  - audit-mcp
  - backend
  - bug
  - performance
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso in TASK-44 (controllo C1). Se nel periodo ci sono depositi o prelievi, performance_service._get_cashflows_with_fallback (performance_service.py ~270) considera flussi esterni solo depositi e prelievi, ma la valutazione storica (repository/_transactions.py, fold ~636-649) aggiunge le quote comprate senza togliere il costo dalla liquidità e non aggiunge i proventi delle vendite. Esempio: deposito 500, acquisto 10 x 100 a prezzo costante -> TWR +200% invece di 0%. Il test tests/unit/test_audit_section_c.py::test_twr_deposit_then_buy_at_flat_price_is_zero (xfail strict) documenta il caso. Riguarda Parent e Wealth, che hanno depositi e prelievi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Con depositi/prelievi nel periodo, acquisti e vendite spostano valore fra liquidità e titoli senza creare rendimento (test xfail che diventa verde, marker rimosso)
- [ ] #2 Decisione documentata su come modellare la liquidità quando gli acquisti superano i depositi registrati (liquidità negativa vs flusso implicito)
- [ ] #3 Test con deposito+acquisto, vendita+prelievo, mix di periodi con e senza depositi, perimetro aggregato
- [ ] #4 Confronto prima/dopo del TWR di un portafoglio sintetico documentato in docs/audit-mcp-2026-11
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 decisione approvata (opzione A): gli acquisti vengono pagati dalla liquidità; la parte non coperta dalla liquidità disponibile è un flusso esterno implicito (apporto). Simmetricamente, i proventi delle vendite restano in liquidità (non sono prelievi) finché non c'è un prelievo registrato.
<!-- SECTION:NOTES:END -->
