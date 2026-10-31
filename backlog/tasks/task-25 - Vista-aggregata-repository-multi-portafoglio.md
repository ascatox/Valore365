---
id: TASK-25
title: 'Vista aggregata: repository multi-portafoglio'
status: Done
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
- [x] #1 Query di _positions, _summary, _transactions e utilities usate dalla performance accettano portfolio_ids (where portfolio_id = any(:ids)); le funzioni a id singolo delegano alla versione multi senza cambiare comportamento
- [x] #2 Posizioni dello stesso asset in portafogli diversi fuse in una riga: quantità sommata, costo medio ponderato, pesi ricalcolati sul totale
- [x] #3 Validazione comune dello scope: id deduplicati, almeno uno, tutti dell'utente (altrimenti not found), stessa valuta base (altrimenti errore 400 con messaggio chiaro)
- [x] #4 PerformanceService: cache con chiave sulla tupla ordinata degli id; TWR/MWR/drawdown calcolati su valori e flussi esterni combinati
- [x] #5 Test unitari: fusione posizioni, summary aggregato = somma dei singoli, TWR aggregato coerente, scope con valute diverse rifiutato, nessuna regressione sui test esistenti
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Nuovo `app/repository/_scope.py`: `normalize_portfolio_ids`, `PortfolioScope` (ids normalizzati, valuta base, `cache_key` ordinata), `load_scope_portfolios` (una query `id = any(:ids)`; errori "Seleziona almeno un portafoglio" / "Portfolio non trovato" / "...stessa valuta base") e `repo.resolve_portfolio_scope(ids, user_id)` (+ funzione `resolve_portfolio_scope(repo, ids, user_id)`). Uno scope di un solo id passa da `_get_portfolio_for_user` come i metodi a id singolo.
- Varianti multi nel repository: `get_positions_multi`, `get_summary_multi`, `get_allocation_multi`, `get_period_performers_multi`, `get_timeseries_multi`, `get_intraday_timeseries_multi`, `get_current_cash_balance_value_multi`, `get_portfolio_inception_date_multi` (min), `get_external_cashflows_multi` / `get_external_cashflows_by_portfolio`, `get_portfolio_values_in_range_multi`. Query con `portfolio_id = any(:portfolio_ids)`; i metodi a id singolo delegano alla versione multi con `[id]` (posizioni, timeseries, intraday, cashflow, valori, inception) oppure condividono lo stesso core (`_summary_from_positions`, `_allocation_from_positions`, `_performers_from_positions`).
- Fusione posizioni: i lotti sono calcolati per (portafoglio, asset) con la stessa logica a costo medio per portafoglio, poi sommati per asset (quantità e costo) → costo medio ponderato, valore di mercato combinato, pesi ricalcolati sul totale. Timeseries, intraday e valori nel periodo tengono le quantità per (portafoglio, asset) e sommano, quindi l'aggregato è la somma esatta dei singoli.
- PerformanceService: tutti i metodi pubblici accettano `int | Sequence[int]` (`PortfolioRef`); una lista di un solo id usa il percorso singolo. Cache per (utente, tupla ordinata degli id). Per gli aggregati lo scope è validato all'apertura della cache; il fallback buy/sell dei flussi è deciso per singolo portafoglio e poi i flussi sono uniti, così i trasferimenti tra portafogli selezionati (prelievo + deposito) si annullano.
- Il Doctor (`run_aggregate_decumulation_plan`) usa `repo.resolve_portfolio_scope`; il portafoglio non dell'utente ora dà "Portfolio non trovato" (sempre 404).
- Nelle risposte con un solo `portfolio_id` (summary e risposte performance) l'aggregato riporta il primo id selezionato: la forma delle risposte aggregate va decisa con le rotte (TASK-26).
- Test: `tests/unit/test_aggregate_repository.py`, `tests/unit/test_performance_aggregate.py`.
<!-- SECTION:NOTES:END -->
