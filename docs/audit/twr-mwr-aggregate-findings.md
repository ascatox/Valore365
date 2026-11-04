# Audit TWR/MWR aggregati — Finding

**Data:** 4 novembre 2026 · **Task:** TASK-55 (TASK-PERF-01..05) · **Perimetro:** vista aggregata Parent
(`portfolio_id = 19`) + Wealth (`portfolio_id = 26`), solo lettura.
**Specifica:** `VALORE365_CLAUDE_AUDIT_TWR_MWR_AGGREGATO.md` (proprietario).

> **Natura delle evidenze.** I finding sono *riprodotti* su fixture sintetiche con valori attesi calcolati
> da un'implementazione di riferimento **indipendente**, scritta nei test (`_ref_twr`, `_ref_npv`,
> `_ref_xirr_roots` in `src/backend/tests/unit/test_performance_golden_audit.py`), mai con
> `calculate_twr`, `calculate_mwr` o `_solve_irr`. I dati reali dei portafogli 19 e 26 **non** sono stati
> letti in questa sessione: si veda `twr-mwr-aggregate-validation.md`. Nessun dato di produzione è stato
> modificato.

## Riepilogo

| ID | Sev. | Classe | Stato | Prima → dopo (fixture) |
|---|---|---|---|---|
| AUDIT-F1 | **P0** | Bug implementativo | Corretto | TWR 0,8333% → **10,0000%** (atteso 10,0000%) |
| AUDIT-F2 | P1 | Differenza di metodologia (finestre disallineate) | Corretto | MWR 12,0469% su 364 gg → **10,0000% su 305 gg** (stessa finestra del TWR) |
| AUDIT-G1 | P1 | Limite del solver (ambiguità non segnalata) | Corretto | `converged=true`, nessun flag → `multiple_roots=true` |
| AUDIT-OBS1 | P0 | Limite di osservabilità MCP | Corretto | MWR assente nel MCP → `mwr_*` per 1m/3m/ytd/1y |
| AUDIT-OBS2 | P0 | Dato mancante per la verifica | Corretto | Solo ultime 20 transazioni → export diagnostico dei flussi datati |
| AUDIT-E2 | P2 | Ambiguità nella contabilizzazione della cassa | Documentato, decisione aperta | Aggregato: +500 netti invece di 0 |
| AUDIT-W1 | P3 | Differenza di metodologia (confine finestra) | Documentato, invariato | — |
| AUDIT-W2 | P3 | Convenzione dei periodi | Documentato, invariato | — |

## AUDIT-F1 — Flusso datato `end` sottratto due volte nel TWR (P0, bug)

- **Causa.** `calculate_twr` (`app/services/performance_service.py`, ciclo dei sottoperiodi) iterava
  `event_days + [end]`. Se esiste un flusso datato `end`, `end` è già in `event_days`. Il secondo
  passaggio usa di nuovo `cf_amount`, perché `day in event_days` è vero, e aggiunge un
  sottoperiodo fittizio `r = (V_end − V_end − cf) / V_end = −cf / V_end`.
- **Impatto.** Per i periodi MCP (`1m`, `3m`, `ytd`, `1y`) `end` è **sempre oggi**. Basta un deposito,
  un prelievo o un **apporto implicito** (un acquisto oltre la cassa) datato oggi per alterare tutti e
  quattro i TWR. Il segno dell'errore dipende dal segno del flusso, la grandezza vale circa
  `cf / V_end`. Il TWR della serie giornaliera (`get_twr_timeseries`, il grafico) non era affetto:
  riepilogo e grafico divergevano proprio nei giorni con movimenti.
- **Riproduzione.** Caso F: valore 1.000 → 1.100 nel periodo, deposito +500 il giorno `end`, valore
  finale 1.600. Atteso 10,0000%; prima 0,8333%, dopo 10,0000%. Lo stesso scenario dell'export
  diagnostico, valutato con l'auditor offline: 3,8448% prima, 7,0899% atteso e dopo.
  Un'esecuzione manuale (deposito 1.000 a inizio, +500 a fine, valore 1.600) dava **−24,375%**
  contro +10% atteso.
- **Correzione.** `end` si aggiunge ai giorni di fine sottoperiodo solo se non è già l'ultimo giorno
  di evento.
- **Test.**
  - `test_f_twr_counts_end_day_flow_exactly_once`;
  - `test_f_twr_with_end_day_flow_matches_daily_timeseries` (TWR del riepilogo = ultimo punto
    della serie giornaliera, tolleranza 1e-4);
  - `test_flow_on_end_date_service_twr_matches_auditor` (export + auditor offline).

## AUDIT-F2 — TWR e MWR su finestre diverse quando il valore iniziale è 0 (P1)

- **Causa.** Con `values[start] <= 0`, `calculate_twr` sposta l'inizio al primo giorno con flusso netto
  positivo, mentre `calculate_mwr` teneva l'inizio richiesto. Ne seguivano `start_date` e
  `period_days` diversi nello stesso riepilogo. In più `_annual_rate_to_cumulative_pct` capitalizzava
  il tasso annuo anche sui giorni in cui non c'era nulla di investito.
- **Riproduzione.** Caso F2: inizio 2025-01-01 con valore 0, primo deposito il 2025-03-01, +10% fino
  alla fine.
  - Prima: TWR su 305 giorni, MWR 12,0469% su 364 giorni.
  - Dopo: entrambi dal 2025-03-01, 305 giorni, MWR 10,0000%.
- **Decisione.** L'MWR adotta la regola del TWR, la stessa finestra e gli stessi giorni di
  valorizzazione. Il tasso annualizzato non cambia; cambia solo il rendimento di periodo, che ora copre
  i giorni effettivamente investiti. Se il valore del nuovo inizio è ≤ 0 (quotazioni mancanti), l'MWR
  è `null` con `converged=false`, come già il TWR.
- **Test aggiornato.** `test_performance_service.py::test_mwr_trade_fallback_mid_period_buy` fissava il
  vecchio comportamento disallineato (43,86% di periodo calcolato su 365 giorni per 183 giorni investiti).
  Ora attende l'inizio al giorno dell'acquisto, 183 giorni e 20%.
- **Rilevanza per 19+26.** È bassa: l'inizio di ogni finestra è limitato alla data del primo movimento,
  quindi il valore iniziale è normalmente > 0. Il caso si presenta con quotazioni mancanti all'inizio
  della finestra.

## AUDIT-G1 — Radici IRR multiple non segnalate (P1)

- **Causa.** `_solve_irr` contava i cambi di segno dell'NPV su 12 punti e si limitava a un warning nei
  log. Con radici vicine (flussi −100 / +230 / −132 a un anno di distanza, radici 10% e 20%) la griglia
  non le distingueva. Newton partendo da 0,1 restituiva una radice e `calculate_mwr` riportava
  `converged=true` senza alcun avviso.
- **Correzione.**
  - Nuovo campo `MWRResult.multiple_roots: bool = False`, retrocompatibile.
  - `_irr_root_count` scandisce l'NPV su circa 400 punti in [−99%, +1000%], più fitti in [−50%, +100%].
  - La scansione gira solo in `calculate_mwr`, non nelle serie storiche.
  - Il solver non è stato sostituito, perché non è emersa una prova riproducibile di un suo errore.
- **Esposizione.** `mwr_multiple_roots` nel MCP; flag di radici multiple nell'auditor offline.
- **Test.** `test_g_multiple_roots_is_flagged_ambiguous`, `test_g_single_root_cases_are_not_flagged`,
  `test_g_root_count_helper_matches_reference`.

## AUDIT-OBS1 — MWR non osservabile via MCP (P0, TASK-PERF-01)

`_get_performance` (`app/copilot_tools.py`) serializzava solo `ps.twr`. Ora espone, con **una sola**
chiamata a `get_performance_summary` per periodo e i campi legacy invariati:

- `mwr_1m`, `mwr_3m`, `mwr_ytd`, `mwr_1y`;
- `mwr_converged`, `mwr_null_reason`, `mwr_multiple_roots`;
- `twr_annualized_pct`, `mwr_annualized_pct` (solo per finestre di almeno 365 giorni);
- `calculation_windows`, con le date di TWR e MWR per periodo;
- `performance_note`.

Test: `tests/unit/test_mcp_performance_mwr.py`. Include il confronto con il servizio reale sull'aggregato
`[1, 2]` per i quattro periodi.

## AUDIT-OBS2 — Flussi datati non disponibili per una verifica indipendente (P0, TASK-PERF-02)

- **Problema.** `get_aggregate_recent_transactions` restituisce solo 20 righe e non distingue i flussi
  impliciti, quindi non basta per un XIRR annuale.
- **Export diagnostico.** `app/services/performance_audit.py::build_performance_audit_export` ricava i
  flussi con le **stesse** funzioni interne del servizio e li riattribuisce per portafoglio. Per ogni
  flusso espone `portfolio_id`, `source` (`transaction` | `cash_model`), `synthetic_flow` e
  `in_twr_mwr`. Il risultato contiene anche:
  - i flussi netti per data;
  - le valorizzazioni sulle date dei flussi;
  - i risultati del servizio;
  - un `consistency_check` che confronta l'insieme dei flussi con `_get_cashflows_with_fallback`;
  - la qualità dei dati (`fx_missing`, `prices_missing`);
  - la paginazione (massimo 500 flussi, 200 via MCP).
- **Accesso.** Tool MCP `get_aggregate_performance_audit`: pesante, in sola lettura, limitato
  all'utente autenticato tramite `resolve_portfolio_scope`.
- **Auditor offline.** `scripts/audit/twr_mwr_offline_auditor.py` usa solo la libreria standard e
  ricalcola TWR e XIRR. Esce con codice 1 se lo scarto supera 0,01 punti percentuali.
- **Limite.** I tool aggregati accettano solo `portfolio_ids` (schema verificato da
  `test_mcp_server.py`), quindi il tool MCP è fisso su `1y`, offset 0. Gli altri periodi e la
  paginazione completa sono disponibili chiamando la funzione Python.

## AUDIT-E2 — Trasferimento da un portafoglio senza cassa registrata (P2, decisione aperta)

- **Comportamento.** Parent registra un prelievo di 500 senza cassa sufficiente, Wealth un deposito di
  500 lo stesso giorno. Il modello di cassa (`settle_day`, `_cash_model.py`) trasforma lo scoperto di
  Parent in un **apporto implicito** di +500, che compensa il prelievo dentro Parent. In aggregato resta
  quindi solo il +500 di Wealth: un'entrata esterna netta invece di un trasferimento a saldo 0.
- **Impatto.** TWR e MWR restano corretti, perché la valorizzazione segue la stessa regola. Crescono
  però di 500 `net_invested` e `implicit_contributions` dell'aggregato, ed è una fonte plausibile di
  parte dei **541.307,64 EUR** di apporti impliciti storici osservati.
- **Test.** `test_e_transfer_from_portfolio_without_cash_reads_as_net_inflow`, marcato `AUDIT-FINDING`,
  verifica il comportamento attuale.
- **Decisione richiesta al proprietario.** Il trasferimento va abbinato esplicitamente (stesso giorno,
  stesso importo e stessa valuta) prima della chiusura di cassa giornaliera, o va corretto lo storico di
  Parent registrando il deposito mancante? Nessuna compensazione è stata forzata.

## AUDIT-W1 — Confine della finestra: guadagno assoluto vs TWR/MWR (P3, metodologia)

`get_performance_summary` usa per `initial_value` / `absolute_gain` il valore di fine giornata di
`start − 1` e conta i flussi del giorno `start`. `calculate_twr` e `calculate_mwr` partono invece dal
valore di fine giornata di `start`, che include già i flussi di quel giorno. Le due convenzioni sono
coerenti al loro interno e senza doppi conteggi (verificato dal caso F), ma coprono finestre che
differiscono di un giorno di mercato. Resta documentato e invariato; `calculation_windows` espone le date.

## AUDIT-W2 — Convenzione dei periodi (P3)

`1m` = 30 giorni, `3m` = 90 giorni, `1y` = 365 giorni di calendario fino a oggi (non mesi solari);
`ytd` = dal 1° gennaio. Il conteggio è ACT/365, anche negli anni bisestili. I valori sono di fine
giornata e non ci sono timestamp intraday: tutti i flussi di un giorno sono trattati come avvenuti a
fine giornata. La convenzione è esplicitata in `performance_note` e `valuation_method`.

## Verifiche senza anomalie

| Caso | Esito |
|---|---|
| A — anno senza flussi | TWR = MWR periodo = MWR annualizzato = 10,0000% |
| B — deposito a metà periodo | TWR 10,0000%; MWR 10,4873% (≠ TWR), residuo NPV −0,0003 EUR |
| C — vendita interna senza prelievo | nessun flusso esterno, TWR = MWR = 0 |
| D — acquisto senza deposito | un apporto implicito di 1.000 nella data dell'acquisto; cassa 0; nessun guadagno fittizio |
| E1 — trasferimento con cassa disponibile | flusso netto aggregato 0; TWR = MWR = 0 |
| E3 — aggregato vs media | TWR aggregato 2,4390% (singoli +10% e −10%; la media sarebbe 0%) |
| G0 — flussi dello stesso segno | `mwr_pct = null`, `converged = false` |
| Solver | prelievo parziale (23,6713%), prelievo totale (10%), finestra di 500 gg (coerenza periodo/annualizzato), finestra di 30 gg (annualizzato `null`) |

## Decisioni contabili non risolvibili dal solo codice

1. **Provenienza degli apporti impliciti** (541.307,64 EUR storici, 80.784,69 EUR nell'ultimo anno).
   Sono depositi reali non registrati, storici incompleti, trasferimenti di titoli o trasferimenti fra
   Parent e Wealth (AUDIT-E2)? Le date sono quelle dello scoperto di cassa, non quelle effettive dei
   bonifici: l'export le marca con `synthetic_flow=true`.
2. **Abbinamento dei trasferimenti fra portafogli** (AUDIT-E2).
3. **Trasferimenti di titoli in entrata**, senza deposito né prezzo di carico affidabile.
4. **Granularità intraday.** Senza timestamp, la regola di fine giornata è un'approssimazione nei giorni
   con forti movimenti di prezzo.
