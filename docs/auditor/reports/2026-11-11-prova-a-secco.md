# Auditor dei calcoli — sessione dell'agente, 2026-11-11 (prova a secco)

Prova a secco di TASK-82: una sessione completa eseguita seguendo `docs/auditor/agent-playbook.md`
come farebbe l'agente settimanale, sul seed dell'Auditor (`scripts/auditor/audit_seed.sql`). Unica
differenza dalla sessione programmata: nessun ramo e nessuna PR (la apre la sessione che coordina).

## 1. Sintesi

| voce | valore |
|---|---|
| data | 2026-11-11 (settimana ISO 46 → area di partenza 46 mod 8 = **6, performance e liquidità**) |
| commit di `main` esaminato | `bb1dd48` (albero di lavoro con le modifiche in corso di TASK-80 e TASK-83, non committate) |
| stack | `scripts/auditor/agent_stack.sh start`: PostgreSQL 16, schema + 36 migrazioni (compresa quella di TASK-80, non ancora su `main`) + seed in ~2 s |
| durata | ~10 minuti di orologio dall'avvio dello stack all'ultima chiamata (11:43–11:52 UTC), più la stesura del report e dei task; 3,1 s di calcolo complessivo nei tool |
| chiamate | **187** a `mcp_call.py` (registro `$AGENT_DIR/mcp_calls.jsonl`), su 32 tool distinti; 9 risposte di errore, tutte attese (argomenti fuori schema, vendita oltre la posizione, simbolo inesistente, X-Ray vuoto) |
| Auditor | 1 esecuzione della CLI, `--mode agent --fail-on P2`: 52 regole, 27 scope, 423 risultati in 2,9 s, codice di uscita 0 |
| sospetti | 4 **confermati**, 2 **da riesaminare**, 6 **scartati** |
| task proposti | TASK-84 (P1), TASK-85 (P2), TASK-86 (P2), TASK-87 (P2), milestone `m-1` |

## 2. Esito dell'Auditor

```bash
cd src/backend && python3 -m app.services.auditor --user auditor-seed-user --mode agent \
  --fail-on P2 --json-out "$AGENT_DIR/work/auditor.json" --md-out "$AGENT_DIR/work/auditor.md"
```

| severità | pass | fail | skip | error |
|---|---:|---:|---:|---:|
| P0 | 30 | 0 | 16 | 0 |
| P1 | 136 | 0 | 85 | 0 |
| P2 | 102 | 0 | 54 | 0 |
| **totale** | **268** | **0** | **155** | **0** |

Nessun `fail` né `error`; difetti noti 0 (B-PAC-SUM dà `pass` sul seed, TASK-83). I 155 `skip`
sono quelli documentati da TASK-79 (9106 vuoto, portafogli senza target, regole non applicabili
allo strumento). Rispetto alla prima esecuzione di TASK-79 i due `fail` di
D-DOCTOR-CONCENTRATION sono spariti (tolleranza `T_pp1`).

## 3. Sospetti confermati

#### S-2026-11-11-01 — Il Doctor e lo Scenario Lab vedono 0 € di liquidità
- Area: doctor
- Tool e argomenti: `build_doctor_scenario` `{"portfolio_id": 9101, "mode": "manual", "operations": [{"symbol": "AUDBD.MI", "action": "buy", "amount": 5000}], "constraints": {"use_cash_balance": true}}`; `get_cash_balance` `{"portfolio_id": 9101}`
- Riproduzione: `python3 scripts/auditor/mcp_call.py build_doctor_scenario '{"portfolio_id": 9101, "mode": "manual", "operations": [{"symbol": "AUDBD.MI", "action": "buy", "amount": 5000}], "constraints": {"use_cash_balance": true}}'`
- Output (estratto): `{"feasible": false, "infeasible_code": "insufficient_cash", "infeasible_reason": "Gli acquisti (5.000 € con i costi) superano la liquidità disponibile (0 €): mancano 5.000 €.", "required_new_cash": 5000.0, "before": {"invested_value": 100000.0, "cash_value": 0.0, "total_value": 100000.0}}`; `get_cash_balance`: `{"total_cash": 9256.5, "cash_breakdown": {"opening_balance": 0.0, "deposits": 100000.0, "dividends": 62.5, "buys": 95704.5, "sells": 4898.5}}`
- Osservato: `before.cash_value` = 0,00; `before.total_value` = 100.000,00; scenario infattibile
- Atteso: `before.cash_value` = `get_cash_balance.total_cash` = 9.256,50; `total_value` = 109.256,50 (= `market_value + cash_balance` del riepilogo); scenario fattibile con 4.256,50 € residui. Con `{"mode": "new_cash_only", "new_cash": 100.0}` `cash_value` è 0 su tutti i portafogli non vuoti (attesi 9.256,50 / 8.144,00 / 2.492,00 / 3.705,97 / 5.545,00 / 4.047,00) e sull'aggregato 9101…9107 (atteso 33.190,47)
- Motivo: domanda 4 (coerenza fra tool: la liquidità del Doctor non è quella di riepilogo, saldo di cassa e ribilanciamento) e 8 (conservazione: la liquidità disponibile sparisce)
- Riferimenti nel codice: `app/services/doctor_policy/snapshot.py:_load_scope` somma `portfolios.cash_balance`, che da TASK-49 è il saldo di apertura (`methodology.md` §8, `_utilities.py` `opening_balance`), non la liquidità del modello della performance (ipotesi, non correzione)
- Deduplica: regole controllate D-CASH-CONSISTENCY, D-DOCTOR-* (nessuna legge `cash_value`); task controllati TASK-47, TASK-49 (ha allineato riepilogo, ribilanciamento, Monte Carlo, non il Doctor), TASK-77; `docs/doctor2/open-decisions.md` OP-15 (riguarda il default di `use_cash_balance`, non il valore); report precedenti: nessuno
- Severità proposta: P1 (numero incoerente fra tool; nessuna metrica del Doctor cambia perché escludono la liquidità, D02)
- Stato: **confermato** → **TASK-84**

Bozza di regola:

```markdown
### D-DOCTOR-CASH
- **Titolo:** La liquidità del Doctor è la stessa del riepilogo
- **Sev.** P1 · **Area** doctor · **Finding** S-2026-11-11-01 · **Scope** portfolio, aggregate
- **Tool:** `build_doctor_scenario` `{"mode": "new_cash_only", "new_cash": 100.0}` (per l'aggregato
  `ctx.scoped`, che aggiunge `portfolio_ids`); `scoped("get_portfolio_summary")`; `get_cash_balance`
  per lo scope portfolio.
- **Condizione:** con c = `before.cash_value` e s = `cash_balance` del riepilogo:
  `|c − s| ≤ T_eur` (nessuna posizione `type == "cash"` nel seed; con posizioni cash
  `|c − s − Σ market_value delle righe cash| ≤ T_sum_eur(n)`); scope portfolio anche
  `|s − total_cash| ≤ T_eur`; `|before.total_value − (before.invested_value + c)| ≤ T_eur`.
- **Tolleranze:** `T_eur` (importi a 2 decimali; `cash_value` del Doctor non arrotondato).
- **Skip:** funzione spenta → `feature_disabled`. Il portafoglio vuoto **non** è `skip`
  (`before` è presente anche con `infeasible_code: "empty_portfolio"`; atteso 0 = 0).
- **Prova:** 9101, 9104, 9106, aggregato (nessuna modifica del seed).
- **Difetto:** snapshot che legge `portfolios.cash_balance` (saldo di apertura) come liquidità.
```

#### S-2026-11-11-02 — Scostamento dal target e ribilanciamento danno pesi diversi allo stesso strumento
- Area: rebalance
- Tool e argomenti: `get_target_drift` `{"portfolio_id": 9101}`; `calculate_rebalance_orders` `{"portfolio_id": 9101}`
- Riproduzione: `python3 scripts/auditor/mcp_call.py get_target_drift '{"portfolio_id": 9101}'` e `python3 scripts/auditor/mcp_call.py calculate_rebalance_orders '{"portfolio_id": 9101}'`
- Output (estratto): drift `[{"symbol": "AUDEQ.MI", "current_weight": 70.0, "target_weight": 50.0, "drift": 20.0}, {"symbol": "AUDBD.MI", "current_weight": 20.0, "drift": -20.0}, {"symbol": "AUDTECH.DE", "current_weight": 10.0, "target_weight": 10.0, "drift": 0.0}]`; ribilanciamento `[{"side": "sell", "symbol": "AUDEQ.MI", "current_weight_pct": 64.07}, {"side": "buy", "symbol": "AUDBD.MI", "current_weight_pct": 18.31}, {"side": "buy", "symbol": "AUDTECH.DE", "amount_eur": 925.65, "current_weight_pct": 9.15, "target_weight_pct": 10.0}], "tolerance_pp": 0.5`
- Osservato: `drift[AUDTECH.DE].current_weight` 10,0 (in linea) contro `orders[AUDTECH.DE].current_weight_pct` 9,15 (0,85 pp sotto, oltre la banda di 0,5, comprato)
- Atteso: lo stesso peso attuale per lo stesso strumento e lo stesso target, o un denominatore dichiarato in `get_target_drift`. Ricalcolo: 10.000 / 100.000 = 10,00 % (solo posizioni) contro 10.000 / 109.256,50 = 9,15 % (con la liquidità, decisione 9)
- Motivo: domanda 2 (denominatore diverso fra tool che mostrano lo stesso numero) e 11 (la descrizione di `get_target_drift` dice «utile per capire se serve ribilanciare», la guida utente MCP abbina i due tool alla stessa domanda)
- Riferimenti nel codice: `app/copilot_tools.py` `_get_target_drift` (pesi di `get_positions`) e `services/rebalance.py` (totale con la liquidità); anche `_calculate_pac_contribution` usa i pesi delle sole posizioni (ipotesi)
- Deduplica: regole controllate B-REB-* (solo sul ribilanciamento), B-PAC-UNDERWEIGHT-ONLY (usa i simboli di `get_target_drift`, non i pesi); task controllati TASK-39 (decisione 9, solo ribilanciamento), nessun task su `get_target_drift`; `decisions.md` 9 e 10; report precedenti: nessuno
- Severità proposta: P2 (coerenza secondaria: gli ordini sono corretti secondo la decisione 9)
- Stato: **confermato** → **TASK-85**

Bozza di regola (da adattare alla decisione del task):

```markdown
### B-DRIFT-REBALANCE-WEIGHTS
- **Titolo:** Scostamento dal target e ribilanciamento partono dagli stessi pesi
- **Sev.** P2 · **Area** rebalance · **Finding** S-2026-11-11-02 · **Scope** portfolio
- **Tool:** `get_target_drift`; `calculate_rebalance_orders` con R (`{}`); `get_portfolio_summary`.
- **Condizione:** per ogni ordine o di R con lo stesso `symbol` in `drift`:
  `|o.current_weight_pct − d.current_weight × MV / (MV + C)| ≤ T_pp2` se `get_target_drift`
  mantiene il denominatore delle posizioni e lo dichiara (MV = `market_value`, C = `cash_balance` del
  riepilogo, più `available_cash`), altrimenti `|o.current_weight_pct − d.current_weight| ≤ T_pp2`;
  `|o.target_weight_pct − d.target_weight| ≤ T_pp`.
- **Tolleranze:** `T_pp2` (due pesi arrotondati a 2 decimali e un rapporto), `T_pp`.
- **Skip:** `empty_portfolio`; `no_targets`; nessun ordine in R → `not_applicable`.
- **Prova:** 9101.
- **Difetto:** pesi del drift sulle sole posizioni senza dichiarazione (stato del 2026-11-11).
```

#### S-2026-11-11-03 — La variazione giornaliera percentuale esclude dal denominatore le posizioni senza chiusura precedente
- Area: daily
- Tool e argomenti: `get_portfolio_summary` `{"portfolio_id": 9107}`; `get_positions` `{"portfolio_id": 9107}`; `get_day_movers` `{"portfolio_id": 9107}`
- Riproduzione: `python3 scripts/auditor/mcp_call.py get_portfolio_summary '{"portfolio_id": 9107}'`
- Output (estratto): `{"market_value": 16000.0, "day_change": -14.11, "day_change_pct": -0.13, "stale_price_symbols": ["AUDSTL.MI"]}`; posizioni `AUDSTL.MI` 6.000 (−0,19, ferma), `AUDEQ.MI` 5.000 (−0,28), `AUDNPC.MI` 5.000 (0); day movers `"valid_positions": 1, "excluded_stale": 1, "excluded_no_previous_close": 1`
- Osservato: `day_change_pct` −0,13 (denominatore 11.025,46 €)
- Atteso: −0,09: valori precedenti da `get_positions` (valore / (1 + variazione %)): `AUDEQ.MI` 5.014,04, `AUDSTL.MI` 6.011,42, `AUDNPC.MI` 5.000 a variazione nulla, come una quotazione ferma → −14,11 / 16.025,46 = −0,088 %. Senza `AUDNPC.MI`: −14,11 / 11.025,46 = −0,128 % (il valore mostrato). Aggregato 9101…9107: −0,13 mostrato contro −0,12 atteso (−297,37 / 236.126,93 contro / 241.126,93)
- Motivo: domande 2 e 3 (denominatore e perimetro non dichiarati: `data_quality_note` cita solo la quotazione ferma) e 11; il codice stesso tiene le quotazioni ferme nel denominatore perché «toglierle gonfierebbe day_change_pct», ma toglie le posizioni senza chiusura precedente
- Riferimenti nel codice: `app/repository/_summary.py`, ciclo di `previous_market_value`: `continue` su «only N bars … and no tick previous_close» prima di `previous_market_value += ...` (ipotesi)
- Deduplica: regole controllate C-DAYMOVERS-NONZERO-INCLUDED, C-DAYMOVERS-CONSISTENCY (solo `get_day_movers`); task controllati TASK-33, TASK-44 (variazione della singola posizione, `previous_close_available`); `audit-findings.md` C3 e `methodology.md` §9 (denominatore «valore precedente delle posizioni», quotazioni ferme incluse; il caso senza chiusura precedente non è trattato); report precedenti: nessuno
- Severità proposta: P2 (trasparenza; differenza di 0,04 pp su 9107)
- Stato: **confermato** → **TASK-86**

Bozza di regola:

```markdown
### C-DAYCHANGE-DENOMINATOR
- **Titolo:** La variazione giornaliera del portafoglio è calcolata su tutte le posizioni
- **Sev.** P2 · **Area** daily · **Finding** S-2026-11-11-03 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_portfolio_summary")`, `scoped("get_positions")`.
- **Condizione:** solo se tutte le posizioni sono nella valuta base (la variazione della posizione è
  in valuta di quotazione, quella del riepilogo al cambio): con
  P = Σ `market_value / (1 + day_change_pct / 100)` su tutte le righe (una riga senza chiusura
  precedente ha `day_change_pct` 0 e conta col suo valore, come una quotazione ferma che il riepilogo
  tratta a variazione nulla) e P ≠ 0: `|day_change_pct − day_change / P × 100| ≤ 0,01 pp`.
- **Tolleranze:** 0,01 pp = `T_pp` del riepilogo più l'errore su P dovuto alle variazioni delle
  posizioni arrotondate a 2 decimali (≤ 0,005 % di ogni valore) e a `day_change` a 2 decimali.
- **Skip:** `empty_portfolio`; valute diverse dalla base → `not_applicable`; output troncato →
  `truncated_output`; `day_change == 0` e nessuna riga con variazione → `no_reference_data`.
- **Prova:** 9107 (fermo + senza chiusura precedente + valido), 9101, aggregato senza 9104.
- **Difetto:** posizione senza chiusura precedente esclusa da `previous_market_value`.
```

Nota per il task: per l'aggregato la condizione vale solo con membri tutti in valuta base senza
valute estere (9104 ha `AUDUS.L` e `AUDUK.L`); sul codice attuale 9107 dà `fail` (−0,13 contro
−0,088).

#### S-2026-11-11-04 — X-Ray di un portafoglio vuoto: errore generico invece di un esito vuoto
- Area: classification
- Tool e argomenti: `get_xray_summary` `{"portfolio_id": 9106}`
- Riproduzione: `python3 scripts/auditor/mcp_call.py get_xray_summary '{"portfolio_id": 9106}'` (con `--debug` si vede l'eccezione)
- Output (estratto): `{"error": "Errore nell'esecuzione del tool get_xray_summary"}`; con `--debug`: `ValueError: Portafoglio non trovato o vuoto` in `compute_portfolio_xray`
- Osservato: errore generico, lo stesso di un guasto
- Atteso: un esito vuoto dichiarato o un errore esplicito, come gli altri tool su 9106: `get_stress_test` `{"scenarios": []}`, `get_cost_breakdown` con campi `null`, `get_portfolio_health` punteggio 0 e livelli `unknown`, `build_doctor_scenario` `infeasible_code: "empty_portfolio"` con un motivo
- Motivo: domanda 7 (caso limite: il tool dà un errore non chiaro); domanda 4 (gli altri tool trattano il caso)
- Riferimenti nel codice: `app/services/portfolio_doctor/_xray.py:compute_portfolio_xray` (`raise ValueError`), `app/copilot_tools.py:_get_xray_summary`, messaggio mascherato in `app/mcp_server/tools.py:_run_portfolio_tool` (ipotesi)
- Deduplica: regole controllate D-XRAY-SUMS (`skip` su 9106); task: nessuno; `architecture.md` Deviazioni TASK-78 annota il comportamento per le regole ma non lo propone come difetto; report precedenti: nessuno
- Severità proposta: P2
- Stato: **confermato** → **TASK-87**

Bozza di regola:

```markdown
### D-XRAY-EMPTY
- **Titolo:** L'analisi X-Ray di un portafoglio vuoto risponde senza errori
- **Sev.** P2 · **Area** classification · **Finding** S-2026-11-11-04 · **Scope** portfolio
- **Tool:** `get_positions`; `ctx.try_call("get_xray_summary")`.
- **Condizione:** se `positions == []`: nessun errore, oppure un errore il cui messaggio non è quello
  generico «Errore nell'esecuzione del tool get_xray_summary»; senza errore,
  `top_underlying_holdings == []`, `geographic_exposure` e `sector_exposure` vuoti o al 100%
  «Non classificato», `coverage_pct` 0 o null.
- **Tolleranze:** nessuna.
- **Skip:** portafoglio non vuoto → `not_applicable`.
- **Prova:** 9106.
- **Difetto:** `ValueError` di `compute_portfolio_xray` mascherato dal server.
```

## 4. Sospetti da riesaminare e scartati

### 4.1 Da riesaminare (criteri 1 o 2 non soddisfatti)

#### S-2026-11-11-05 — Sovrapposizione del 55% fra un ETF di titoli di Stato e un ETF high yield
- Area: doctor
- Tool e argomenti: `get_portfolio_health` e `read_doctor_metrics` `{"portfolio_id": 9102}`
- Output (estratto): `"overlap": "moderate"`, `score_deductions` `overlap_over_50` (4 + 8 punti, «Sovrapposizione 55.0 (> 50)»), alert «Diverse posizioni risultano ridondanti: la sovrapposizione tra ETF è alta (55.0%)»; metrica `etf_overlap_pct` 55,0 con contributori `AUDGOV.MI` e `AUDHY.DE`
- Motivo: titoli di Stato in euro e obbligazioni societarie high yield non condividono emittenti;
  il 55 viene da una costante (`estimate_overlap_between_assets`: due bond della stessa regione → 55,0)
- Perché non promosso: criterio 2 non soddisfatto. L'euristica è dichiarata («Misura euristica»)
  e il seed non ha top holdings obbligazionarie con cui dimostrare la sovrapposizione reale. Da
  riesaminare con un seed che abbia le partecipazioni di due ETF obbligazionari (§6)
- Riferimenti: `app/services/portfolio_doctor/_health.py:estimate_overlap_between_assets`
- Deduplica: nessuna regola sull'overlap; nessun task
- Stato: sospetto

#### S-2026-11-11-06 — Il what-if simula l'acquisto di un simbolo inesistente
- Area: simulation
- Tool e argomenti: `calculate_what_if` `{"portfolio_id": 9101, "action": "buy", "symbol": "ZZZNOPE", "amount_eur": 5000}`
- Output (estratto): `{"new_weight": 4.76, "max_position_weight_after": 66.67, "impact_on_concentration": "migliora"}`; `search_asset_info` sullo stesso simbolo: `{"error": "Asset non trovato per il simbolo: ZZZNOPE"}`; `build_doctor_scenario` rifiuta un asset non posseduto (`unknown_asset`, `docs/doctor2/api-contracts.md`)
- Motivo: domanda 7 (un simbolo sbagliato produce un risultato sicuro invece di un errore)
- Perché non promosso: criterio 2 non soddisfatto. Il calcolo è giusto per un acquisto ipotetico
  di uno strumento nuovo (5.000 / 105.000 = 4,76 %) e il tool usa solo l'importo: nessun numero è
  sbagliato. Da riesaminare se una decisione dice che il what-if accetta solo strumenti noti
- Deduplica: B-WHATIF-BUY-WEIGHT, B-WHATIF-SELL-BOUND (simboli posseduti); nessun task
- Stato: sospetto

### 4.2 Scartati

| sigla | osservazione | motivo |
|---|---|---|
| S-2026-11-11-07 | 9107: `get_positions` mostra −0,19 % per `AUDSTL.MI`, ferma da 30 giorni, mentre il riepilogo la conta a variazione nulla | criterio 3: dichiarato (`price_stale`, `stale_reason`, `data_quality_note` «variazione giornaliera di queste posizioni non aggiornata»; `get_day_movers` la esclude, C-DAYMOVERS-CONSISTENCY passa) |
| S-2026-11-11-08 | 9103: `equity_weight_pct.value` 29,41 e `gold_weight_pct.value` 47,06 con denominatore «valore investito escluso cash», contro pesi 25 / 40 | criterio 3: metodologia del Doctor (`docs/doctor2/financial-methodology.md` §2: `value = K / coverage × 100`, `lower`/`upper` per la quota non classificata, nota «Quota non classificata: 15,0%») |
| S-2026-11-11-09 | 9101, 9104, 9107: finestra «1y» di 300 giorni o meno, rendimento non annualizzato | criterio 3: dichiarato (`calculation_windows`, `performance_note`, annualizzati null sotto 365 giorni) |
| S-2026-11-11-10 | 9104: `cost_basis` del riepilogo 26.404,59 contro acquisti di cassa 26.404,58 | criterio 4: arrotondamento della somma di tre costi a 2 decimali (`T_sum_eur(3)`) |
| S-2026-11-11-11 | 9103: X-Ray «Oro (asset class)» 39,99 nella geografia e 40,0 nei settori | criterio 4: arrotondamento per far sommare la geografia a 100 (D-XRAY-SUMS passa) |
| S-2026-11-11-12 | 9105: 48 € di dividendi incassati negli ultimi 12 mesi ma reddito stimato 0 | criterio 3: `missing_yield_symbols` dichiara `AUDEQ.MI` senza rendimento; è un ETF ad accumulazione con dividendi nel seed (proposta §6) |

## 5. Copertura dell'esplorazione

- **Area della settimana (6, performance e liquidità), domande 1-8 su 9101…9107 e aggregato:**
  `get_performance`, `get_cash_balance`, `get_portfolio_summary`, `get_positions`,
  `get_recent_transactions` su tutti i portafogli; `get_aggregate_performance`,
  `get_aggregate_summary`, `get_aggregate_performance_audit`. Ricalcoli: scomposizione della
  liquidità di 9101 (100.000 + 62,50 + 4.898,50 − 95.704,50 = 9.256,50), costo medio di `AUDEQ.MI`
  dopo la vendita (700/750 × 67.501,50 = 63.001,40), plusvalenza 9,64 %, TWR 9101 = rendimento
  semplice 9,2565 % (nessun flusso dopo il deposito), TWR dell'aggregato dai valori alle date dei
  flussi dell'export (7,0489 %, uguale a `service_results`; passa anche D-PERF-RECOMPUTE), variazione giornaliera di 9101, 9107 e
  dell'aggregato (S-03). Portafoglio vuoto 9106: TWR null, MWR 0, liquidità 0.
- **Altre aree, domande 4 e 7:** costi, reddito, dividendi, salute, X-Ray, stress, variazioni
  giornaliere, Monte Carlo, drift, metriche e violazioni del Doctor, freschezza su tutti i
  portafogli; stress, X-Ray, salute, posizioni, allocazione e Monte Carlo aggregati. Confronti:
  valore (riepilogo = Σ posizioni = costi), TER (costi / salute / Doctor), peso massimo, liquidità
  (riepilogo / saldo / Doctor → S-01), reddito (proiezione / dividendi). Casi limite: PAC e what-if
  con importi 0 e negativi (rifiutati dallo schema), PAC e ribilanciamento senza target e su 9106,
  what-if su strumento nuovo, inesistente (S-06), fermo e oltre la posizione, ribilanciamento
  `buy_only` / `sell_only` / con `available_cash`, Scenario Lab manuale, oltre la posizione,
  `use_cash_balance` (S-01), ribilanciamento, aggregato e su 9106, `search_asset_info` su simboli
  sconosciuti e non classificati.
- **Domande non applicate:** 9 (classificazione) e 10 (dati importati) solo dove un tool le
  toccava per caso; area 2 (classificazione e X-Ray) e 8 (Doctor) solo con le domande 4 e 7.
- **Dove ci si è fermati:** Monte Carlo e stress a shock non ricalcolati (coperti da C-MC-* e
  A-STRESS-*); `compare_doctor_scenarios` e `validate_policy_draft` non esplorati; nessuna policy
  del Doctor salvata nel seed, quindi violazioni e regole del Doctor non esercitate.

## 6. Proposte di miglioramento del seed

- `AUDEQ.MI` è un ETF «(Acc)» ma riceve dividendi in 9104 e 9105: usare uno strumento a
  distribuzione (o un nome «(Dist)») per i dividendi, così il reddito stimato e quello incassato
  sono confrontabili (S-12).
- Un portafoglio con `portfolios.cash_balance` iniziale diverso da 0, per esercitare il saldo di
  apertura nel modello della liquidità e la regola D-DOCTOR-CASH su entrambi i termini.
- Top holdings di due ETF obbligazionari (con e senza emittenti in comune) per verificare
  l'euristica della sovrapposizione (S-05).
- Una policy del Doctor salvata su un portafoglio (per esempio 9101), così le violazioni, lo
  Scenario Lab con regole e `compare_doctor_scenarios` hanno qualcosa da valutare.
- Un portafoglio con più di 30 posizioni per esercitare `truncated_output` (già annotato da TASK-78).
