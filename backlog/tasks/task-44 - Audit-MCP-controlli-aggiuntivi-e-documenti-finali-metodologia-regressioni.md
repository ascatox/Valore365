---
id: TASK-44
title: 'Audit MCP: controlli aggiuntivi e documenti finali (metodologia, regressioni)'
status: Done
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T10:53:00Z'
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
- [x] #1 Ogni controllo della sezione C ha esito documentato (confermato / non riprodotto / issue aperta)
- [x] #2 methodology.md con formule, unità, denominatori, copertura e limiti
- [x] #3 regression-results.md con i comandi eseguiti e il loro esito
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Da TASK-33: aggiungere a Position un indicatore di chiusura precedente mancante, così day_change_pct=0.0 di default non viene scambiato per una giornata piatta.

Da TASK-35/36: il quote type Yahoo BOND trasforma ancora un etf in bond al refresh; _get_dividend_summary e search_asset_info usano ancora get_asset_by_symbol (match debole sul ticker base).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fix residui: Position.previous_close_available e day movers senza chiusura precedente esclusi; il quote type BOND non trasforma più etf/fund in bond; dividend summary e search_asset_info risolvono per asset_id/simbolo esatto (match: exact/different_listing); dividendi divisi per valuta con totale null se misti. Controlli della sezione C con test su dati sintetici (tests/unit/test_audit_section_c.py): problemi aperti come TASK-46 (TWR: acquisti contati come rendimento con depositi, P1), TASK-47 (cambio incoerente e fallback silenziosi), TASK-48 (trasparenza X-Ray). Documenti in docs/audit-mcp-2026-11/: audit-findings.md, methodology.md, regression-results.md, decisions.md. Test: 820 passed, 1 xfailed.
<!-- SECTION:FINAL_SUMMARY:END -->
