---
id: TASK-38
title: 'Audit MCP: stress test storici indipendenti dal portafoglio senza dati'
status: In Progress
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-02T18:37:00Z'
labels:
  - audit-mcp
  - backend
  - bug
milestone: m-1
dependencies:
  - TASK-35
  - TASK-37
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-001. Quando nessuna posizione ha almeno 2 barre di prezzo nella finestra dello scenario, run_stress_test restituisce benchmark_drawdown*0.8 (_stress.py:95-101), identico per ogni portafoglio. Sostituire con la metodologia scelta in TASK-37 (scenario non disponibile con coverage_pct oppure proxy per asset class) e documentarla.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Nessun valore indipendente dal portafoglio presentato come stima individuale
- [ ] #2 Ogni scenario espone coverage_pct, metodo (storico/proxy/non disponibile) e contributo per asset class
- [ ] #3 Test riproducibili su 100% azioni, 100% bond, 60/40, All Weather, portafoglio vuoto e copertura parziale
- [ ] #4 Metodologia descritta nella documentazione MCP
<!-- AC:END -->
