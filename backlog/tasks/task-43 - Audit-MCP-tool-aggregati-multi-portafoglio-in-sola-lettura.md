---
id: TASK-43
title: 'Audit MCP: tool aggregati multi-portafoglio in sola lettura'
status: In Progress
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T10:24:00Z'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 scelta (proposta dall'assistente, avviata con 'start'): tool dedicati con prefisso get_aggregate_* e parametro portfolio_ids (2-20 id, stessa valuta) invece di modificare lo schema dei tool esistenti; ogni chiamata conta una volta sul rate limit, quelle pesanti sulla quota pesante.
<!-- SECTION:NOTES:END -->
