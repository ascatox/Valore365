---
id: TASK-36
title: 'Audit MCP: proiezione del reddito con classificazione obbligazionaria corretta'
status: In Progress
assignee: []
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-02T17:32:00Z'
labels:
  - audit-mcp
  - mcp
  - backend
  - bug
milestone: m-1
dependencies:
  - TASK-35
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-004. _get_income_projection legge asset_type da get_asset_by_symbol, che restituisce solo id/symbol/name: tutto finisce in equity, anche i bond. In più FIXED_INCOME_TYPES={'bond'} esclude gli ETF obbligazionari. Usare p.asset_type da get_positions e il classificatore di TASK-35. Correggere anche il match debole di get_asset_by_symbol sul ticker base.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 IHYG e FRC3 (sintetici) finiscono nel reddito fisso
- [ ] #2 equity + fixed_income + unknown = reddito lordo proiettato
- [ ] #3 Gli strumenti non classificati vanno in un bucket unknown esplicito, mai in equity per default
- [ ] #4 L'ipotesi fiscale è dichiarata nell'output (tax_note) secondo TASK-37
- [ ] #5 Test con ETF bond, ETF equity, distribuzione/accumulazione, yield mancante e categoria sconosciuta
<!-- AC:END -->
