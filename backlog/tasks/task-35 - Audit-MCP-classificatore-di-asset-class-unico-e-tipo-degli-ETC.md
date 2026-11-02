---
id: TASK-35
title: 'Audit MCP: classificatore di asset class unico e tipo degli ETC'
status: To Do
assignee: []
created_date: '2026-11-02T17:22:00Z'
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
- [ ] #1 Un classificatore condiviso è usato da stress, health, X-Ray e reddito
- [ ] #2 Test di classificazione per ETF azionario, ETF obbligazionario, ETC oro, ETN, bond, stock e asset sconosciuto
- [ ] #3 Nello scenario US Tech Crash bond, oro e commodity non ricevono lo shock equity se non è dichiarato nella tabella
- [ ] #4 Per ogni shock l'output indica classi colpite, shock applicati e contributi
- [ ] #5 XAD1.DE (ETC oro) non viene più trattato come singola azione con TER 0
<!-- AC:END -->
