---
id: TASK-35
title: 'Audit MCP: classificatore di asset class unico e tipo degli ETC'
status: Done
assignee: []
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-02T17:48:00Z'
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
V365-002 e V365-012. Esistono più classificatori incoerenti: _stress._shock_asset_class (solo bond/equity), _holdings._asset_class, instant_portfolio_analyzer.map_asset_class. Bond ETF tipizzati etf, ETC tipizzati stock (QUOTE_TYPE_MAP, import CSV), simboli senza nome che finiscono in equity. Creare un classificatore unico (asset_type -> investment_focus/category di arricchimento -> nome -> simbolo) con classe unknown esplicita; aggiungere le chiavi commodity/gold agli SHOCK_SCENARIOS; most_impacted esclude impatti nulli o positivi; non degradare etf a stock durante il refresh dei prezzi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un classificatore condiviso è usato da stress, health, X-Ray e reddito
- [x] #2 Test di classificazione per ETF azionario, ETF obbligazionario, ETC oro, ETN, bond, stock e asset sconosciuto
- [x] #3 Nello scenario US Tech Crash bond, oro e commodity non ricevono lo shock equity se non è dichiarato nella tabella
- [x] #4 Per ogni shock l'output indica classi colpite, shock applicati e contributi
- [x] #5 XAD1.DE (ETC oro) non viene più trattato come singola azione con TER 0
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Da TASK-34: infer_ter restituisce 0 per asset_type=bond (ora marcato inferred); con il classificatore unico va rivisto per i fondi/ETF obbligazionari.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Classificatore unico app/services/asset_classification.py (asset_type -> arricchimento ETF/categoria -> nome -> simbolo/ISIN; classe unknown esplicita) usato da stress, health/holdings, X-Ray e instant analyzer. XAD1.DE/DE000A1EK0G3 classificato gold. SHOCK_SCENARIOS con shock espliciti gold/commodity/crypto (PROVVISORI, da approvare in TASK-37). Output degli shock: affected_classes, class_breakdown (peso, shock, contributo), flags; most_impacted solo perdite reali. Refresh prezzi non degrada etf/fund a stock. infer_ter non restituisce 0 per ETC/bond ETF tipizzati stock. Test: tests/unit/test_asset_classification.py.
<!-- SECTION:FINAL_SUMMARY:END -->
