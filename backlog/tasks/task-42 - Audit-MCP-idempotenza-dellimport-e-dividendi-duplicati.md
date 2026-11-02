---
id: TASK-42
title: 'Audit MCP: idempotenza dell''import e dividendi duplicati'
status: In Progress
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-02T20:21:00Z'
labels:
  - audit-mcp
  - backend
  - dati
  - import
milestone: m-1
dependencies:
  - TASK-37
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-009. Le transazioni non hanno id esterno, hash di provenienza né vincolo di unicità; commit_batch non è atomico (un doppio commit è possibile); un nuovo upload dello stesso file reinserisce le righe. get_recent_transactions non espone l'id. get_dividend_summary somma valute diverse senza FX.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 commit_batch è atomico (claim con status 'committing' e un'unica transazione DB)
- [ ] #2 Le righe importate hanno import_batch_id e source_hash; l'anteprima avvisa dei duplicati
- [ ] #3 Reimportare lo stesso file non duplica; due movimenti legittimamente identici restano importabili secondo la regola decisa
- [ ] #4 get_recent_transactions espone l'id della transazione
- [ ] #5 Audit in sola lettura dei duplicati esistenti, senza cancellazioni automatiche
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Query di verifica in sola lettura: backlog/docs/AUDIT_MCP_2026-11_QUERY_DATI.sql (in attesa dei risultati dal proprietario).
<!-- SECTION:NOTES:END -->
