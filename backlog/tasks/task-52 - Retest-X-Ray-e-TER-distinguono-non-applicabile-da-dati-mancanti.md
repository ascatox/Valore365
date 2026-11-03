---
id: TASK-52
title: 'Retest: X-Ray e TER distinguono ''non applicabile'' da ''dati mancanti'''
status: Done
assignee: []
created_date: '2026-11-03T13:26:00Z'
updated_date: '2026-11-03T13:39:00Z'
labels:
  - audit-mcp
  - backend
  - mcp
milestone: m-1
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Retest MCP 2026-11-03 §4 (X-Ray e TER) e analisi §6. Copertura X-Ray 0% su All Weather e 14,2% su 100% Azionario: oro, materie prime e bond senza look-through vengono contati come dati mancanti. TER mancanti per TLT, IEF, DJP, GLD (ETF USA) e VEUR.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 X-Ray: per ogni posizione lookthrough_status = available | not_applicable | missing, con motivo
- [x] #2 Copertura calcolata anche sulla sola parte applicabile (applicable_lookthrough_coverage_pct) con denominatore dichiarato
- [x] #3 TER: fonti verificabili (justETF, yFinance expense ratio) per gli strumenti mancanti quando disponibili, sempre con ter_source; nessun valore inventato
- [x] #4 Test su All Weather (TLT, IEF, VTI, DJP, GLD) e 100% Azionario (VTI, VEUR, VFEM)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
X-Ray: lookthrough_status (available/not_applicable/missing) con motivo per posizione; oro, materie prime, crypto, monetari e obbligazioni sono non applicabili (X-Ray solo azionario); applicable_lookthrough_coverage_pct e quote available/not_applicable/missing che sommano a 100; card con testo e badge. Bug: gli errori di rete di Yahoo venivano salvati in cache come 'nessuna holding' per un'ora; ora sollevano ProviderError e vengono riprovati. TER: extract_expense_ratio_pct legge netExpenseRatio, annualReportExpenseRatio ed expenseRatio, e il TER si recupera anche dai metadati grezzi già salvati; nuovo POST /api/portfolios/{id}/asset-metadata/backfill; etf-enrichment/backfill?refresh_missing_ter=true include gli ETC tipizzati stock. Test: test_xray_lookthrough_status.py, test_ter_sources_task52.py, XRayCard.test.tsx; 961 passed backend, 142 frontend. Da eseguire: i due backfill sui portafogli coinvolti.
<!-- SECTION:FINAL_SUMMARY:END -->
