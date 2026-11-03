---
id: TASK-48
title: 'X-Ray: copertura e denominatori trasparenti'
status: Done
assignee: []
created_date: '2026-11-03T10:53:00Z'
updated_date: '2026-11-03T13:12:00Z'
labels:
  - audit-mcp
  - backend
milestone: m-1
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso in TASK-44 (controllo C6). coverage_pct indica solo che un fondo ha qualche top holding, non quanta parte del fondo è vista; esposizioni geografiche e settoriali non sommano a 100; manca la data di riferimento dei dati.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 coverage_pct definito come quota del portafoglio effettivamente scomposta, con denominatore esplicito
- [x] #2 Quota non classificata esposta in modo che le esposizioni sommino a 100
- [x] #3 Data di riferimento dei dati del provider nell'output
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Copertura X-Ray con denominatore esplicito (valore delle posizioni, liquidità esclusa): lookthrough_coverage_pct (quota effettivamente scomposta: peso del fondo x somma delle top holding), funds_with_holdings_pct, classified_country/sector_pct, coverage_note. Esposizioni geografiche e settoriali che sommano a 100 con 'Non classificato' e bucket per asset class (oro, obbligazioni, materie prime). Data dei dati per fondo (data_source, data_as_of) e data complessiva. Card X-Ray: 'Scomposto il X% del portafoglio', data del provider, badge per ETF. Test: test_xray_coverage.py (11), XRayCard.test.tsx (4), test MCP aggregato; 870 passed backend, 140 frontend. Aperti: singoli titoli ancora tra i coverage_issues e non tra le aggregated_holdings; aggregated_holdings con la vecchia base se ci sono posizioni di tipo cash.
<!-- SECTION:FINAL_SUMMARY:END -->
