---
id: TASK-50
title: 'Retest: DBXP e VEUR classificati unknown (nomi abbreviati del broker)'
status: Done
assignee: []
created_date: '2026-11-03T13:15:00Z'
updated_date: '2026-11-03T13:23:00Z'
labels:
  - audit-mcp
  - backend
  - bug
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Retest MCP 2026-11-03, V365-002 parziale. DBXP.DE ('XTR2 EGB13 1CC', ISIN LU0290356871, ~6,39% di Parent) e VEUR ('Azioni Europa') risultano unknown: le regole per nome non riconoscono le abbreviazioni dei broker (EGB = Euro Government Bond) né 'azioni', e l'arricchimento justETF/yFinance per questi ISIN probabilmente manca. In US Tech Crash DBXP riceve lo shock equity (-30%) invece di quello bond. Analisi in backlog/docs/RETEST_MCP_2026-11-03_ANALISI.md §1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Classificazione per ISIN tramite l'arricchimento (justETF), recuperato se mancante, con fonte dichiarata
- [x] #2 Fallback motivato per nomi abbreviati dei broker (EGB, GOVT, TREAS, azioni, obblig, ...) con test
- [x] #3 DBXP -> bond e VEUR -> equity in stress, reddito, X-Ray e health (test)
- [x] #4 Nessuna regressione sulle classificazioni esistenti
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Causa: con etf_enrichment mancante restava solo il nome abbreviato del broker, e EGB/azioni non erano riconosciuti; reddito e instant analyzer non passavano ISIN/index_tracked al classificatore. Soluzione: loader unico load_classification_inputs (ISIN, categoria, focus, indice, nome justETF) per holdings e reddito; nome justETF come fonte strutturata; fallback con tabelle esplicite di abbreviazioni (source=name_abbrev, solo parole intere, segnali in conflitto -> unknown). Endpoint POST /api/portfolios/{id}/etf-enrichment/backfill per arricchire gli asset senza dati (nessuna chiamata di rete nei percorsi di lettura). DBXP -> bond, VEUR -> equity in stress, reddito, X-Ray, health. Test: test_asset_classification_broker_names.py; 932 passed. Senza arricchimento restano unknown, dal solo nome Fineco: 0GGH, SE15, EUN5, EQQQ, TDIV (nel DB reale sono arricchiti; il backfill copre i casi mancanti).
<!-- SECTION:FINAL_SUMMARY:END -->
