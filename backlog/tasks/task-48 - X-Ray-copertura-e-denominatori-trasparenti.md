---
id: TASK-48
title: 'X-Ray: copertura e denominatori trasparenti'
status: To Do
assignee: []
created_date: '2026-11-03T10:53:00Z'
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
- [ ] #1 coverage_pct definito come quota del portafoglio effettivamente scomposta, con denominatore esplicito
- [ ] #2 Quota non classificata esposta in modo che le esposizioni sommino a 100
- [ ] #3 Data di riferimento dei dati del provider nell'output
<!-- AC:END -->
