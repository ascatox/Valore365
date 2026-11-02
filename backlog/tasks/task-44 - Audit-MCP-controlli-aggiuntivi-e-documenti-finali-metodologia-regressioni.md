---
id: TASK-44
title: 'Audit MCP: controlli aggiuntivi e documenti finali (metodologia, regressioni)'
status: To Do
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-02T17:48:00Z'
labels:
  - audit-mcp
  - docs
milestone: m-1
dependencies:
  - TASK-33
  - TASK-34
  - TASK-35
  - TASK-36
  - TASK-38
  - TASK-39
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sezioni C e G del documento di audit: riconciliazione TWR/MWR, segno e valuta dei movimenti di cassa, coerenza tra day_change e summary, timestamp e valuta dei prezzi, income yield vs total return, copertura X-Ray, nota fiscale, tolleranza sulle quantità frazionarie. Produrre methodology.md e regression-results.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ogni controllo della sezione C ha esito documentato (confermato / non riprodotto / issue aperta)
- [ ] #2 methodology.md con formule, unità, denominatori, copertura e limiti
- [ ] #3 regression-results.md con i comandi eseguiti e il loro esito
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Da TASK-33: aggiungere a Position un indicatore di chiusura precedente mancante, così day_change_pct=0.0 di default non viene scambiato per una giornata piatta.

Da TASK-35/36: il quote type Yahoo BOND trasforma ancora un etf in bond al refresh; _get_dividend_summary e search_asset_info usano ancora get_asset_by_symbol (match debole sul ticker base).
<!-- SECTION:NOTES:END -->
