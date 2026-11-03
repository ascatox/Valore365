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
