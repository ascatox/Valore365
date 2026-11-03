# Audit MCP 2026-11 — Risultati delle regressioni

Esecuzione del 2026-11-03 sul ramo di lavoro di TASK-44 (base `main` @ `4813870`, dopo le PR #61,
#62, #63). Nessun accesso a database reali: repository finti e righe SQL scriptate.

## Backend

```bash
cd src/backend
python -m pytest tests/unit/test_audit_leftovers_task44.py -q      # prima della correzione
# 12 failed, 4 passed

python -m pytest tests/unit/test_audit_leftovers_task44.py -q      # dopo la correzione
# 16 passed

python -m pytest tests/unit/test_audit_section_c.py -q
# 8 passed, 1 xfailed

python -m pytest tests/unit/test_audit_section_c.py -q --runxfail -k deposit_then_buy
# 1 failed: assert 200.0 == 0.0  (issue aperta C1-TWR-MIXED, vedi audit-findings.md)

python -m pytest tests/unit tests/integration/test_mcp_server.py tests/integration/test_api_behavior.py -q
# 820 passed, 1 xfailed   (baseline prima di TASK-44: 796 passed)
```

Test nuovi: 16 in `tests/unit/test_audit_leftovers_task44.py` (parte 1) e 9 in
`tests/unit/test_audit_section_c.py` (sezione C, di cui 1 `xfail(strict=True)` che documenta
l'issue aperta e fallirà quando sarà corretta). Test esistenti aggiornati:
- `tests/unit/test_asset_classification.py`: il caso `("etf", "BOND")` ora si aspetta `etf`.
- `tests/unit/test_copilot_day_movers_monte_carlo.py`: le posizioni di prova dichiarano
  `previous_close_available=True`.

Test di regressione dei task precedenti (inclusi nel conteggio): `test_copilot_day_movers_monte_carlo.py`,
`test_mcp_tool_limits.py`, `test_cost_breakdown_ter.py`, `test_asset_classification.py`,
`test_stress_historical_proxy.py`, `test_rebalance_plan.py`, `test_volatility_and_score_breakdown.py`,
`test_csv_import_dedup.py`, `test_performance_service.py`, `test_summary_day_change.py`,
`test_mcp_server.py` (contratto MCP e tool aggregati), `test_api_behavior.py`.

## Frontend (`src/frontend/valore-frontend`)

```bash
npm run lint          # nessun errore (eslint --max-warnings 0)
npx vitest run        # Test Files 25 passed (25) — Tests 134 passed (134)
npx tsc -b            # 140 errori, uguale alla baseline (140): nessun errore nuovo
```

Unica modifica: campo opzionale `previous_close_available?: boolean` nell'interfaccia `Position`
(`src/services/api/types.ts`), additivo.

## Copertura

Non è stata misurata la copertura del codice (nessun `pytest-cov` nel flusso del progetto). I
moduli toccati dall'audit hanno test dedicati elencati sopra.

## Rischi residui

1. **TWR con depositi e acquisti nella stessa finestra:** corretto in TASK-46 (vedi la sezione
   "TASK-46" sotto).
2. **Dati non ancora corretti:** PARTE A (39 acquisti ×1000 di Wealth) e PARTE B (21 duplicati) di
   `backlog/docs/AUDIT_MCP_2026-11_CORREZIONE_DATI.sql` attendono l'esecuzione del proprietario:
   fino ad allora quantità, valore di mercato e dividendi di Wealth restano errati.
3. **Valuta dei listing `.L` (TASK-41):** `quote_currency = EUR` su tutti i `.L`; prezzi in GBP/USD
   letti come EUR; senza FX il prezzo della posizione resta il costo medio senza avviso.
4. **Commissioni Fineco contate due volte (TASK-45):** costo di carico gonfiato e quantità non intere.
5. **Cassa in valute diverse:** `get_cash_balance` (FX più recente) e `summary.cash_balance` (FX alla
   data) divergono; FX mancante = 1,0. Nessun effetto oggi (tutto EUR).
6. **X-Ray:** `coverage_pct` misura la presenza di top holdings, non la profondità; nessuna data di
   riferimento.
7. **Proxy degli stress in USD:** effetto cambio non modellato (dichiarato all'utente).
8. **Limiti in memoria per processo:** con N istanze i limiti MCP sono N volte più larghi.
9. **Asset creati fuori dalla transazione atomica dell'import** (TASK-42).
10. **Periodo 1D dei period performers** riusa `day_change_pct` delle posizioni: per una posizione
    senza chiusura precedente vale 0 (ora distinguibile con `previous_close_available`, non ancora
    usato lì).

## TASK-46 — modello di liquidità e apporti impliciti (2026-11-03)

```bash
cd src/backend
python -m pytest tests/unit/test_audit_section_c.py tests/unit/test_performance_cash_model.py -q
# 21 passed   (l'ex xfail test_twr_deposit_then_buy_at_flat_price_is_zero ora passa, marker rimosso)

python -m pytest tests/unit tests/integration/test_mcp_server.py tests/integration/test_api_behavior.py -q
# 833 passed  (prima: 820 passed, 1 xfailed; +12 test nuovi, +1 ex xfail)
```

Frontend non toccato (campo backend additivo `implicit_contributions` in `PerformanceSummary`).

Confronto prima/dopo su portafogli sintetici (valutazione reale del repository, righe scriptate;
prezzo piatto 100 salvo dove indicato; casi in `tests/unit/test_performance_cash_model.py`):

| Caso | TWR prima | TWR dopo | MWR prima | MWR dopo |
|---|---|---|---|---|
| A. Deposito 1000, acquisto 10 × 100 | +100% | 0% | n.d. | 0% |
| B. Deposito 500, acquisto 10 × 100 (500 apporto implicito) | +200% | 0% | n.d. | 0% |
| C. Deposito 1000, acquisto 10, vendita 5, prelievo 500 | +50% | 0% | n.d. | 0% |
| D. Depositi 1000 (g0) e 600 (g100), acquisti 10 × 100 e 5 × 110, prezzo 100→110→121 (g200) | +39,23% | +20,68% (atteso a catena 1,10 × 1,09706) | +35,79% | +20,61% |
| E. Deposito 2000, commissioni 10 + 3 + imposte 2 + movimento `fee` 15 | +24,25% | −1,50% | n.d. | −1,50% |
| F. Senza depositi, solo acquisti, prezzo 100→110→121 | +21% | +21% (invariato) | +21% | +21% |
| G. Senza depositi, acquisto 10, vendita 5 a 110, prezzo →121 | +21% | +15,5% (proventi in liquidità) | +21% | +15,5% |

Test aggiornati (aspettative che codificavano il comportamento precedente):
- `test_transactions_repository.py::test_batch_valuation_pins_absolute_values` e
  `::test_batch_valuation_clamps_oversized_sell_at_zero`: la valutazione ora scala gli acquisti
  dalla liquidità e vi accredita i proventi delle vendite.
- `test_performance_aggregate.py::test_a_transfer_between_selected_portfolios_nets_out`: i dati
  finti registrano il deposito iniziale (un prelievo senza liquidità registrata genera un apporto
  implicito); TWR atteso invariato (10%).
- `test_performance_aggregate.py::test_aggregate_fallback_to_trades_is_decided_per_portfolio`
  → `test_aggregate_cash_model_is_applied_per_portfolio`: l'acquisto compare come
  `implicit_contribution` (non più come flusso `buy`) e il flag vale "solo apporti impliciti";
  TWR atteso invariato (0%).

## TASK-47 — liquidità: un solo cambio, nessun ripiego silenzioso, dividendi netti (2026-11-03)

```bash
cd src/backend
python -m pytest tests/unit/test_cash_fx_task47.py -q
# 14 passed   (prima delle modifiche: 13 failed, 1 passed)

python -m pytest tests/unit tests/integration/test_mcp_server.py tests/integration/test_api_behavior.py -q
# 847 passed  (prima: 833 passed; +14 test nuovi, nessuna aspettativa esistente cambiata)
```

Frontend (`src/frontend/valore-frontend`, solo campi opzionali aggiunti in `services/api/types.ts`):
`npm run lint` pulito; `npx vitest run` 134 passed (25 file); `npx tsc -b` 140 errori (baseline
invariata).

Prima → dopo su dati sintetici (`tests/unit/test_cash_fx_task47.py`):

| Caso | Prima | Dopo |
|---|---|---|
| Saldo iniziale 200 + deposito 1000 + dividendo 100 USD (cambio 0,90 alla data, 0,95 ultimo) | summary 1290, `total_cash` 1295 | entrambi 1290 |
| Stesso caso senza cambi USD | 1300 in entrambi, nessun avviso | 1300, `fx_missing_currencies = ["USD"]` |
| Dividendo 100 con ritenuta 26 (+ deposito 1000) | liquidità 1100, valore performance 1100, flusso `dividend` 100 | 1074 in summary, `get_cash_balance`, valutazione storica; flusso `dividend` 74 |
| Titolo quotato in USD senza cambio; titolo senza prezzi | prezzo = costo medio senza segnalazione | stesso valore, `price_fallback = 'avg_cost'`, `fx_missing` (solo il primo), elencati in `price_fallback_symbols` |

Test esistente adattato: `tests/unit/test_summary_day_change.py` (il finto repository espone anche
`get_current_cash_balance_detail`, usato ora dal summary).

## TASK-49 — liquidità del summary = modello di liquidità della performance (2026-11-03)

Decisione del proprietario: opzione 1 (methodology §9.1). Saldo iniziale `portfolios.cash_balance`
= liquidità disponibile prima della prima transazione, sia nella liquidità corrente sia nella storia
della performance (fold dei valori + `deposit` esterno nel giorno della prima transazione).

```bash
cd src/backend
python -m pytest tests/unit/test_cash_model_task49.py -q
# 11 passed   (test nuovi)

python -m pytest tests/unit tests/integration/test_mcp_server.py tests/integration/test_api_behavior.py -q
# 858 passed  (prima: 847 passed; +11 test nuovi, 6 aspettative aggiornate, sotto)
```

Frontend (`src/frontend/valore-frontend`): `npm run lint` pulito; `npx vitest run` 136 passed
(26 file, +2 test `CashSection.test.tsx`); `npx tsc -b` 140 errori (baseline invariata, nessuno nei
file toccati).

Prima → dopo (`tests/unit/test_cash_model_task49.py`, prezzo finale 110):

| Caso | Liquidità prima | Liquidità dopo | Totale summary prima | Totale summary dopo = valore performance |
|---|---|---|---|---|
| §9.1: deposito 1000, acquisto 8 × 100, vendita 3 × 110, dividendo 20 (ritenuta 5,20) | 1014,80 | 544,80 | 1564,80 | 1094,80 |
| Solo operazioni: acquisto 10 × 100, vendita 4 × 110, acquisto 1 × 110 | 0 | 330 (apporti impliciti 1000) | 770 | 1100 |
| §9.1 con saldo iniziale 200 | 1214,80 | 744,80 | 1764,80 | 1294,80 (prima la performance dava 1094,80: saldo iniziale escluso) |
| Deposito 100, prelievo 150, deposito 20 | −30 | 20 (apporto implicito 50) | — | — |

Test esistenti aggiornati (codificavano la vecchia semantica):
- `test_aggregate_repository.py::test_aggregated_cash_is_the_sum_of_the_balances`: 1000 / 512 /
  1512 → 400 / 462 / 862 (acquisti scalati, vendite accreditate, scoperto di 300 del portafoglio 2
  come apporto implicito, verificato).
- `test_aggregate_repository.py::test_aggregated_intraday_value_combines_holdings_and_cash`: il
  valore intraday somma la nuova liquidità (1620 + 862 invece di 1620 + 1512).
- `test_audit_section_c.py::test_cash_balance_signs_and_trade_date_fx`: l'acquisto di 999 oltre la
  liquidità (793) ora porta la liquidità a 0 con 206 di apporto implicito (prima ignorato: 793).
- `test_cash_utilities.py::test_compute_cash_balance_base_only_cash_movements` →
  `test_compute_cash_balance_base_follows_the_cash_model`: 400 → 615,10 (acquisto coperto da apporto
  implicito, vendita USD al cambio della data accreditata).
- `test_transactions_repository.py::test_batch_valuation_pins_absolute_values` e
  `::test_batch_valuation_before_first_transaction_matches_empty_portfolio_rule`: il saldo iniziale
  (500 nei dati finti) è ora parte della storia dal giorno della prima transazione (+500 su ogni
  valore).

## Run TASK-48 (2026-11-03) — X-Ray: copertura, denominatori e data dei dati

```bash
cd src/backend
python -m pytest tests/unit/test_xray_coverage.py -q
# 11 passed   (test nuovi)

python -m pytest tests/unit tests/integration/test_mcp_server.py tests/integration/test_api_behavior.py -q
# 870 passed  (prima: 858 passed; +11 test_xray_coverage.py, +1 test MCP get_aggregate_xray, 1 aspettativa aggiornata)
```

Frontend (`src/frontend/valore-frontend`): `npm run lint` pulito; `npx vitest run` 140 passed
(27 file, +4 test `XRayCard.test.tsx`); `npx tsc -b` 140 errori (baseline invariata, nessuno nei
file toccati).

Casi verificati (`tests/unit/test_xray_coverage.py`):

| Caso | Risultato |
|---|---|
| Fondo 50% con top 10 al 45% + fondo 50% senza dati | `lookthrough_coverage_pct` 22,5; `funds_with_holdings_pct` 50; `coverage_pct` 50 (invariato) |
| Fondo 50% (top al 40%) + azione 50% | look-through 70 (azione = sottostante di sé stessa) |
| Paesi 60+30% di un fondo al 60% + fondo senza dati al 40% | USA 36, "Non classificato" 46, somma 100; settori: 60 + 40 non classificato |
| Equity 50% + oro 20% + obbligazionario 30% (solo paesi) | "Oro (asset class)" 20 in paesi e settori; "Obbligazioni (asset class)" 30 nei settori; somme 100 |
| Posizione `cash` 20% | esclusa dal denominatore: USA 100%, look-through 50% del fondo al 50% |
| Nessun dato | look-through 0, "Non classificato" 100, `data_as_of` null, `data_source` none |
| `holdings_date` 30.09.2026 / non leggibile (fetched_at 15/10) | 2026-09-30 (`holdings_date`) / 2026-10-15 (`fetched_at`); complessivo 2026-09-30 |
| Copilot/MCP con 14 paesi | primi 10 + "Altri" + "Non classificato" = 100 |

Test esistente aggiornato: `test_audit_section_c.py::test_xray_coverage_is_weight_with_any_top_holdings_and_exposures_are_on_total`
→ `::test_xray_coverage_has_explicit_denominators_and_exposures_sum_to_100` (la geografia ora include
"Non classificato" 50; `lookthrough_coverage_pct` 10; `data_as_of` presente).
