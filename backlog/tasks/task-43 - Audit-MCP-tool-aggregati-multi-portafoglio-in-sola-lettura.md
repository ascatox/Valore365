---
id: TASK-43
title: 'Audit MCP: tool aggregati multi-portafoglio in sola lettura'
status: Done
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T10:30:00Z'
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
- [x] #1 Aggregati uguali alla vista applicativa entro tolleranze definite
- [x] #2 Un id non autorizzato produce un errore senza fuga di dati (test)
- [x] #3 Nessun tool di scrittura; l'MCP resta in sola lettura
- [x] #4 Documentazione MCP aggiornata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 scelta (proposta dall'assistente, avviata con 'start'): tool dedicati con prefisso get_aggregate_* e parametro portfolio_ids (2-20 id, stessa valuta) invece di modificare lo schema dei tool esistenti; ogni chiamata conta una volta sul rate limit, quelle pesanti sulla quota pesante.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
9 tool MCP get_aggregate_* (summary, positions, allocation, recent_transactions, performance, health, monte_carlo, stress_test, xray) con portfolio_ids (2-20, unici), che riusano le stesse chiamate dei route aggregate dell'app. Tutti gli id passano da resolve_portfolio_scope: errore unico 'Portfolio non trovato' senza dettagli, errore esplicito per valute diverse. performance/health/monte_carlo/stress_test/xray contano sulla quota pesante. Sola lettura (readOnlyHint; X-Ray senza client justETF). Non aggiunti, perché l'app non ha un aggregato: target drift, ribilanciamento, what-if, PAC, dividendi, costi, reddito, day movers. Test: 22 nuovi in test_mcp_server.py; docs aggiornate.
<!-- SECTION:FINAL_SUMMARY:END -->
