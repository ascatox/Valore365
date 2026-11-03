---
id: TASK-47
title: 'Liquidità e prezzi: cambio usato in modo incoerente e fallback silenziosi'
status: Done
assignee: []
created_date: '2026-11-03T10:53:00Z'
updated_date: '2026-11-03T11:40:00Z'
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
- [x] #1 Stesso criterio di cambio fra get_cash_balance e summary, documentato
- [x] #2 Cambio mancante e prezzo ripiegato sul costo segnalati nell'output (flag), non nascosti
- [x] #3 Decisione sulle ritenute dei dividendi documentata e testata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Da TASK-46: summary.cash_balance conta solo i movimenti di cassa (più il cash_balance iniziale) e ignora acquisti e vendite, quindi può essere negativo; la valutazione storica della performance invece applica il modello di liquidità dell'opzione A. Per i portafogli con vendite senza prelievi, il valore corrente della performance supera il totale del summary dell'importo dei proventi. Il cash_balance iniziale (senza data) non entra nello storico. Ritenute sui dividendi ignorate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Helper unico _cash_balance_detail per summary, cash balance REST, MCP get_cash_balance e viste aggregate: movimenti in valuta estera convertiti al cambio della data dell'operazione (stessa regola del modello di liquidità e del costo). Fallback segnalati: Position.price_fallback/fx_missing/fx_missing_currencies, summary fx_missing_currencies/price_fallback_symbols, data_quality_note nei tool MCP. Dividendi netti delle ritenute in tutti i calcoli di liquidità. Test: test_cash_fx_task47.py (14); totale 847 passed. Divergenza fra la liquidità del summary e quella della performance spostata in TASK-49 (decisione del proprietario). Ancora aperto: la valutazione storica usa cambio 1.0 senza flag se il tasso manca.
<!-- SECTION:FINAL_SUMMARY:END -->
