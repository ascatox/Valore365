---
id: TASK-33
title: >-
  Audit MCP: quick win su day movers, Monte Carlo a 10 anni ed errori di rate
  limit
status: To Do
assignee: []
created_date: '2026-11-02T17:22:00Z'
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
- [ ] #1 get_day_movers restituisce best/worst ogni volta che almeno una posizione ha day_change_pct valido e non stale; altrimenti un motivo esplicito
- [ ] #2 get_monte_carlo restituisce esattamente gli anni 1..10 ordinati, con p25<=p50<=p75 e un campo unit
- [ ] #3 Una chiamata rifiutata per concorrenza non consuma la quota dei tool pesanti (test)
- [ ] #4 Gli errori di limite hanno code e retry_after_s strutturati
- [ ] #5 Test unitari che falliscono prima della correzione e passano dopo
<!-- AC:END -->
