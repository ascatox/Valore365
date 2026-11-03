---
id: TASK-41
title: >-
  Audit MCP: valuta di quotazione, GBp e FX mancante nel costo di carico (SE15,
  IBTM)
status: In Progress
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T07:50:00Z'
labels:
  - audit-mcp
  - backend
  - dati
milestone: m-1
dependencies:
  - TASK-37
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-008. Prima di cambiare il codice va fatta un'indagine in sola lettura. Rischi confermati nel codice: quote_currency impostata alla valuta base del portafoglio alla creazione dell'asset (csv_service.py:1058, routes_assets.py:313), fallback silenzioso a FX=1.0 (_positions.py:353), nessuna normalizzazione GBp->GBP, quantità ricavata da controvalore/prezzo nell'import Fineco. Eseguire la query di riconciliazione sui lotti presente nella verifica (in sola lettura, a cura del proprietario).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Riconciliazione per lotti documentata per SE15.L e IBTM.L in entrambi i portafogli
- [ ] #2 Se il bug è confermato: quote_currency dalla valuta del provider, GBp normalizzato, FX mancante segnalato e non sostituito con 1.0
- [ ] #3 Test con strumenti in EUR, USD, GBP e GBX
- [ ] #4 Nessuna modifica silenziosa della storia contabile: un eventuale backfill è un piano separato e approvato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Query di verifica in sola lettura: backlog/docs/AUDIT_MCP_2026-11_QUERY_DATI.sql (in attesa dei risultati dal proprietario).

2026-11-03: Q1-Q4 analizzate (vedi sezione 'TASK-41 — Riconciliazione sui dati' nel documento di verifica). Causa 1 confermata: 17 righe di Wealth con prezzo x1000 e quantità /1000 dovute al parser dei numeri a 3 decimali (già corretto nel codice in b655330, dati da correggere con un piano approvato). Causa 2 da confermare: quote_currency=EUR su tutti i listing .L.
<!-- SECTION:NOTES:END -->
