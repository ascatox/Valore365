---
id: TASK-43
title: 'Audit MCP: tool aggregati multi-portafoglio in sola lettura'
status: To Do
assignee: []
created_date: '2026-11-02T17:23:00Z'
labels:
  - audit-mcp
  - mcp
  - backend
  - feature
milestone: m-1
dependencies:
  - TASK-37
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-011. Aggiungere il supporto multi-portafoglio all'MCP riutilizzando resolve_portfolio_scope e i metodi *_multi del repository (limite di 20 id, stessa valuta, verifica della proprietà di ogni id).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Aggregati uguali alla vista applicativa entro tolleranze definite
- [ ] #2 Un id non autorizzato produce un errore senza fuga di dati (test)
- [ ] #3 Nessun tool di scrittura; l'MCP resta in sola lettura
- [ ] #4 Documentazione MCP aggiornata
<!-- AC:END -->
