---
id: TASK-33
title: >-
  Audit MCP: quick win su day movers, Monte Carlo a 10 anni ed errori di rate
  limit
status: Done
assignee: []
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-02T17:31:00Z'
labels:
  - audit-mcp
  - mcp
  - backend
  - bug
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-005, V365-006 e V365-013 (vedi backlog/docs/AUDIT_MCP_2026-11_VERIFICA.md). Correzioni senza decisioni di metodologia. (1) _get_day_movers legge get_portfolio_target_performance, che contiene rendimenti a 1 anno degli asset target e non variazioni giornaliere: calcolare direttamente da repo.get_positions, escludere i prezzi stale e gestire il default day_change_pct=0.0. (2) _get_monte_carlo: projections[:10] seguito da year>0 restituisce gli anni 1..9: filtrare 1<=year<=10 e dichiarare l'unità (indice base 100). (3) mcp_server/tools.py: la quota dei tool pesanti viene consumata prima del controllo di concorrenza; restituire errori machine-readable {code: concurrency_busy|heavy_quota, retry_after_s} e correggere il testo 'qualche minuto'.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 get_day_movers restituisce best/worst ogni volta che almeno una posizione ha day_change_pct valido e non stale; altrimenti un motivo esplicito
- [x] #2 get_monte_carlo restituisce esattamente gli anni 1..10 ordinati, con p25<=p50<=p75 e un campo unit
- [x] #3 Una chiamata rifiutata per concorrenza non consuma la quota dei tool pesanti (test)
- [x] #4 Gli errori di limite hanno code e retry_after_s strutturati
- [x] #5 Test unitari che falliscono prima della correzione e passano dopo
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
day movers calcolati da get_positions (escluse posizioni stale o senza prezzo, ordinamento stabile, reason esplicito); Monte Carlo esattamente anni 1..10 con unit=indice_base_100; MCP: concorrenza verificata prima della quota pesante, errori di limite come CallToolResult isError con structuredContent {code, message, retry_after_s}. Test: tests/unit/test_copilot_day_movers_monte_carlo.py, tests/unit/test_mcp_tool_limits.py, test_mcp_server.py aggiornato. Limite residuo: una posizione con prezzo fresco ma senza chiusura precedente ha day_change_pct=0.0 di default e non è distinguibile (serve un campo in repository/_positions.py, vedi TASK-44).
<!-- SECTION:FINAL_SUMMARY:END -->
