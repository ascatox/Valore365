---
id: TASK-40
title: 'Audit MCP: health score spiegabile e volatilità con metodologia dichiarata'
status: In Progress
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-02T18:37:00Z'
labels:
  - audit-mcp
  - mcp
  - backend
milestone: m-1
dependencies:
  - TASK-35
  - TASK-37
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-010. Il 16.0 della volatilità nello stress è il pavimento equity a lungo termine (_holdings.py:174,246); la volatilità dell'health è una media ponderata senza correlazioni. Il tool non espone category_scores.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 get_portfolio_health espone category_scores e i fattori che hanno tolto punti
- [ ] #2 Ogni volatilità ha nome, metodo, periodo e flag is_floored
- [ ] #3 Test su punteggio e pavimento
- [ ] #4 Documentazione MCP aggiornata
<!-- AC:END -->
