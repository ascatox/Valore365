---
id: TASK-46
title: >-
  Performance: con depositi nel periodo gli acquisti vengono contati come
  rendimento (TWR)
status: Done
assignee: []
created_date: '2026-11-03T10:53:00Z'
updated_date: '2026-11-03T11:09:00Z'
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
- [x] #1 Con depositi/prelievi nel periodo, acquisti e vendite spostano valore fra liquidità e titoli senza creare rendimento (test xfail che diventa verde, marker rimosso)
- [x] #2 Decisione documentata su come modellare la liquidità quando gli acquisti superano i depositi registrati (liquidità negativa vs flusso implicito)
- [x] #3 Test con deposito+acquisto, vendita+prelievo, mix di periodi con e senza depositi, perimetro aggregato
- [x] #4 Confronto prima/dopo del TWR di un portafoglio sintetico documentato in docs/audit-mcp-2026-11
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 decisione approvata (opzione A): gli acquisti vengono pagati dalla liquidità; la parte non coperta dalla liquidità disponibile è un flusso esterno implicito (apporto). Simmetricamente, i proventi delle vendite restano in liquidità (non sono prelievi) finché non c'è un prelievo registrato.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Modello di liquidità condiviso (app/repository/_cash_model.py, opzione A) usato dalla valutazione storica e dai flussi di TWR/MWR, singoli e aggregati: gli acquisti escono dalla liquidità, i proventi delle vendite restano in liquidità fino a un prelievo; se a fine giornata la liquidità è negativa, la parte scoperta è un apporto implicito (implicit_contribution) e la liquidità torna a 0. Prelievi oltre la liquidità: la parte scoperta è un apporto implicito (uscita netta = liquidità disponibile). MCP get_performance espone implicit_contributions_eur. Esempi: deposito 500 + acquisto 1000 a prezzo costante, TWR da +200% a 0%; depositi a metà periodo con prezzi in movimento, da +39,23% a +20,68% (uguale al calcolo concatenato). Test: test_performance_cash_model.py (12); 4 test aggiornati perché codificavano il comportamento errato. Totale: 833 passed.
<!-- SECTION:FINAL_SUMMARY:END -->
