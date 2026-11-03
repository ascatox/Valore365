---
id: TASK-51
title: >-
  Retest: search_asset_info distingue tipo tecnico, classe e tipo di strumento
  (XAD1)
status: Done
assignee: []
created_date: '2026-11-03T13:15:00Z'
updated_date: '2026-11-03T13:23:00Z'
labels:
  - audit-mcp
  - mcp
  - backend
milestone: m-1
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Retest MCP 2026-11-03, V365-012. search_asset_info(XAD1.DE) restituisce type=stock perché riporta assets.asset_type; le analisi lo trattano già come oro. Senza migrazione, l'output deve esporre asset_class (classificatore condiviso), instrument_type (etc/etn/etf/fund/stock/bond quando determinabile) e classification_source, e dire quale campo usare per allocazione e rischio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 search_asset_info espone asset_class, instrument_type, classification_source mantenendo type
- [x] #2 XAD1.DE -> asset_class gold, instrument_type etc
- [x] #3 Test: XAD1, ETF azionario, ETF obbligazionario, ETN, azione singola
- [x] #4 Descrizione del tool aggiornata
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
search_asset_info mantiene type (tipo tecnico salvato) e aggiunge asset_class, instrument_type, classification_source e classification_note (usare asset_class per allocazione e rischio). XAD1.DE -> gold/etc. Test su XAD1, ETF azionario, DBXP, ETN, azione singola.
<!-- SECTION:FINAL_SUMMARY:END -->
