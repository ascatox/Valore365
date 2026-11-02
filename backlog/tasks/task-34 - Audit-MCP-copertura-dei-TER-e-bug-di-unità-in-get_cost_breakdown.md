---
id: TASK-34
title: 'Audit MCP: copertura dei TER e bug di unità in get_cost_breakdown'
status: In Progress
assignee: []
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-02T17:26:00Z'
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
V365-007. _get_cost_breakdown legge meta.expense_ratio senza normalize_expense_ratio_pct (TER 100 volte più piccolo), somma il costo annuo solo sulle posizioni coperte e calcola il fee_drag sull'intero valore; non espone la copertura. infer_ter restituisce 0 per stock/bond, che vengono contati come coperti. Unificare la fonte del TER con compute_weighted_ter.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il TER da yfinance è normalizzato (0.0075 -> 0.75%) con un test
- [ ] #2 L'output espone ter_coverage_pct (per peso), missing_ter_symbols, ter_source per posizione ed estimated_annual_cost_known_eur
- [ ] #3 fee_drag e costo annuo usano lo stesso perimetro dichiarato
- [ ] #4 Test con copertura 0%, 35%, 75% e 100% senza valori fuorvianti
- [ ] #5 La politica sui TER mancanti segue la decisione presa in TASK-37
<!-- AC:END -->
