---
id: TASK-26
title: 'Vista aggregata: endpoint API in sola lettura'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - backend
  - vista-aggregata
dependencies: [TASK-25]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Esporre la vista aggregata via API seguendo il precedente di GET /portfolios/aggregate/decumulation: rotte /portfolios/aggregate/... con query portfolio_ids ripetuto, registrate prima delle rotte {portfolio_id}.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Endpoint aggregati per summary, positions, allocation, timeseries, intraday-timeseries, performers, performance/* (summary, twr, mwr, timeseries, monthly, yearly, drawdown, rolling, hall-of-fame), monte-carlo, xray, health, stress-test, transactions, data-coverage
- [x] #2 Le transazioni aggregate riportano portfolio_id e portfolio_name per riga
- [x] #3 Errori coerenti: 400 per valute diverse o lista vuota, 404 per portafogli non dell'utente
- [x] #4 Test delle rotte (inclusa la precedenza della rotta aggregate sulle rotte con id)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Nuovo modulo `app/api/routes_aggregate.py` (`register_aggregate_routes`), registrato in `main.py` **prima** di tutti gli altri moduli: ogni rotta `/portfolios/aggregate/...` precede ogni `/portfolios/{portfolio_id}/...` (test sull'ordine reale delle rotte di `app.main` e richiesta HTTP sull'app reale). La rotta `aggregate/decumulation` è stata spostata qui da `portfolio_health.py` (stessi parametri e risposta).
- Endpoint (`GET`, query `portfolio_ids` ripetuto, stessi parametri/modelli delle rotte singole e stessa dipendenza `require_auth_rate_limited`):
  - `/portfolios/aggregate/summary`, `positions`, `allocation`, `performers` (`days`), `timeseries` (`range`, `interval`), `intraday-timeseries`, `transactions`, `data-coverage` (`days`, `threshold_pct`; feature flag Target Allocation come la singola)
  - `/portfolios/aggregate/performance/summary` (`period`), `twr`, `twr/timeseries`, `mwr`, `mwr/timeseries`, `gain/timeseries`, `monthly-returns`, `yearly`, `drawdown`, `rolling-windows` (`window_months`, `risk_free_rate`), `hall-of-fame` (`top_n`)
  - `/portfolios/aggregate/health`, `monte-carlo`, `stress-test`, `xray`, `decumulation`
- Forma delle risposte: modelli invariati. Dove c'è `portfolio_id` l'aggregato riporta `portfolio_id = 0` e il nuovo campo opzionale `portfolio_ids: list[int] | None` con gli id normalizzati (None per le rotte singole, retrocompatibile). Campo aggiunto a `PortfolioSummary`, `DataCoverageResponse`, `MonthlyReturnsResponse`, `YearlyPerformanceResponse`, `DrawdownResponse`, `RollingWindowsResponse`, `HallOfFameResponse` e alle risposte Doctor (`PortfolioHealthResponse`, `MonteCarloProjectionResponse`, `StressTestResponse`, `XRayResponse`, dove `portfolio_id` passa da `ge=1` a `ge=0`). Helper `aggregate_identity(ids)` in `_scope.py`. Ogni input lista (anche di un solo id) è riportato come aggregato: `PerformanceService._response_identity` sostituisce `_response_portfolio_id` (che riportava il primo id) e `get_summary_multi` marca il risultato. `PerformanceSummary`/`TWRResult`/`MWRResult` non hanno `portfolio_id` e restano invariati.
- Transazioni: `repo.list_transactions_multi(ids, user_id)` (scope validato, `join portfolios`, ordine `trade_at desc, id desc` come la singola, nessuna paginazione come la singola); `TransactionListItem.portfolio_name: str | None = None` valorizzato solo per gli aggregati.
- Data coverage: `repo.get_price_coverage_multi(ids, user_id, days)` sull'unione (distinct) degli asset delle allocazioni target dei portafogli; il calcolo è condiviso con la singola (`_coverage_items`). Non c'è un target aggregato: la copertura è dell'unione dei target.
- Doctor: `analyze_portfolio_health`, `run_monte_carlo_projection`, `run_stress_test`, `compute_portfolio_xray` accettano `int | Sequence[int]`; `resolve_doctor_scope` valida lo scope e dà l'identità della risposta. Le holdings aggregate vengono da `get_positions_multi` e sono fuse per `asset_id` (`_merge_holdings_by_asset`, valore e peso sommati): `_load_aggregate_holdings` (decumulo) non elenca più duplicati — prima i duplicati sovrascrivevano il peso nella mappa per asset delle statistiche storiche, ora il peso è quello combinato. Nessuna feature Doctor usa dati per portafoglio non aggregabili (target allocation esclusa).
- Errori: `aggregate_error()` mappa in un solo punto i messaggi fissi dello scope: lista vuota / valute diverse / più di 20 id → 400 `invalid_request`, portafoglio non dell'utente → 404 `not_found`; gli altri ValueError mantengono lo status della rotta singola (404 `not_found` per dashboard/Doctor, 400 `bad_request` per performance/timeseries). La dipendenza `aggregate_portfolio_ids` normalizza gli id e rifiuta lista vuota (anche `portfolio_ids` assente: 400 invece del 422 della vecchia rotta decumulation) e più di `MAX_AGGREGATE_PORTFOLIOS = 20`.
- Rotte singole invariate (unica differenza: `portfolio_ids: null` nelle risposte che hanno `portfolio_id`).
- Test: `tests/unit/test_routes_aggregate.py` (tutti i gruppi di rotte, mappatura errori, limite 20, precedenza sull'app reale), `tests/unit/test_aggregate_views.py` (transazioni aggregate con `portfolio_name`, data coverage, holdings Doctor fuse, identità delle risposte Doctor).
<!-- SECTION:NOTES:END -->
