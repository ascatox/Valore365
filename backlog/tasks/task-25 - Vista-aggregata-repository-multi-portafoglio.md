---
id: TASK-25
title: 'Vista aggregata: repository multi-portafoglio'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - backend
  - vista-aggregata
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Primo passo della vista aggregata virtuale (più portafogli visti come uno solo, senza creare un portafoglio nuovo). Oggi repository e PerformanceService lavorano su un solo portfolio_id. Serve che posizioni, summary, allocazione, timeseries, flussi di cassa esterni, valori nel periodo e data di inizio accettino una lista di portfolio_ids, mantenendo le firme a id singolo come wrapper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Query di _positions, _summary, _transactions e utilities usate dalla performance accettano portfolio_ids (where portfolio_id = any(:ids)); le funzioni a id singolo delegano alla versione multi senza cambiare comportamento
- [ ] #2 Posizioni dello stesso asset in portafogli diversi fuse in una riga: quantità sommata, costo medio ponderato, pesi ricalcolati sul totale
- [ ] #3 Validazione comune dello scope: id deduplicati, almeno uno, tutti dell'utente (altrimenti not found), stessa valuta base (altrimenti errore 400 con messaggio chiaro)
- [ ] #4 PerformanceService: cache con chiave sulla tupla ordinata degli id; TWR/MWR/drawdown calcolati su valori e flussi esterni combinati
- [ ] #5 Test unitari: fusione posizioni, summary aggregato = somma dei singoli, TWR aggregato coerente, scope con valute diverse rifiutato, nessuna regressione sui test esistenti
<!-- AC:END -->
