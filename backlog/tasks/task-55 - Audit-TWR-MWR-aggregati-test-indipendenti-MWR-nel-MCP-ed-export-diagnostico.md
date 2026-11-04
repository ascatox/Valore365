---
id: TASK-55
title: >-
  Audit TWR/MWR aggregati: test indipendenti, MWR nel MCP ed export
  diagnostico
status: In Progress
assignee: []
created_date: '2026-11-04T19:00:00Z'
updated_date: '2026-11-04T19:00:00Z'
labels:
  - backend
  - performance
  - mcp
  - audit
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Specifica del proprietario (VALORE365_CLAUDE_AUDIT_TWR_MWR_AGGREGATO.md, 2026-11-04). Perimetro: vista aggregata Parent (19) + Wealth (26). Verificare in modo indipendente TWR e MWR (XIRR), rendere l'MWR osservabile via MCP in modo retrocompatibile, aggiungere un export diagnostico in sola lettura dei flussi datati e delle valorizzazioni, e test di regressione con valori attesi calcolati indipendentemente (casi A-G). Nessuna modifica ai dati di produzione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Golden test A-G con valori attesi calcolati indipendentemente (non con calculate_twr/calculate_mwr)
- [ ] #2 get_performance / get_aggregate_performance espongono mwr_* senza cambiare i campi twr_* esistenti
- [ ] #3 Export diagnostico read-only dei flussi esterni/impliciti datati e delle valorizzazioni, con auditor offline indipendente
- [ ] #4 Bug individuati corretti con test che falliscono prima e passano dopo
- [ ] #5 Report docs/audit/twr-mwr-aggregate-findings.md e docs/audit/twr-mwr-aggregate-validation.md
<!-- AC:END -->
