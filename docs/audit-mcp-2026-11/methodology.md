# Audit MCP 2026-11 — Metodologia

Formule, unità, denominatori, copertura dei dati, fonti dei parametri e limiti dei modelli usati dai
tool MCP di Valore365 dopo le correzioni dell'audit (TASK-33..44). Tutte le percentuali sono in
**punti percentuali** (1,5 = 1,5%) salvo dove indicato. Valuta: valuta base del portafoglio (EUR).
I riferimenti al codice sono relativi a `src/backend/app/`.

## 1. Stress test (`get_stress_test`, `services/portfolio_doctor/_stress.py`)

**Classe di ogni posizione:** classificatore unico (§10).

**Scenari a shock** (`constants/stress_scenarios.py`, `SHOCK_SCENARIOS`; approvati il 2026-11-02):

| Scenario | equity | bond | cash | gold | commodity | crypto |
|---|---:|---:|---:|---:|---:|---:|
| Global Equity Crash | −20% | −3% | 0 | −5% | −15% | −35% |
| US Tech Crash (×1,5 sui titoli tech) | −30% | +2% | 0 | 0 | −10% | −45% |
| Bond Selloff | −5% | −12% | 0 | −10% | −5% | −10% |
| Emerging Markets Crisis | −25% | −8% | 0 | −5% | −15% | −30% |
| Commodity Drop | −10% | −2% | 0 | −10% | −20% | −10% |

- Impatto = Σ peso_i × shock(classe_i) (modello lineare); `class_breakdown` riporta per classe
  `weight_pct`, `shock_pct`, `contribution_pct`, che sommano all'impatto.
- Classe `unknown`: shock equity prudenziale, flag `unknown_asset_class_equity_shock`.
- `most_impacted`: solo perdite effettive.

**Scenari storici** (GFC 2008, Dot-com 2000-02, Covid 2020, Bear market 2022):
- `coverage_pct` = peso delle posizioni con almeno due prezzi reali nella finestra (la liquidità conta
  come coperta, rendimento 0).
- `coverage_pct ≥ 60%` → `method: "historical"`: parte coperta con i prezzi reali, parte scoperta con
  i proxy di classe (flag `uncovered_weight_filled_with_class_proxy`).
- `< 60%` → `method: "proxy"`: impatto = Σ peso_i × drawdown proxy(scenario, classe_i)
  (`HISTORICAL_CLASS_PROXIES`); portafoglio vuoto → `not_available`.
- **Fonte dei proxy:** rendimento approssimato nella finestra di MSCI World, Bloomberg Global
  Aggregate, oro LBMA, Bloomberg Commodity TR, Bitcoin, **in USD** (valori arrotondati all'unità,
  approvati con la condizione di mostrare il limite all'utente).
- **Limiti:** effetto cambio EUR/USD non modellato (2022: MSCI World circa −13% e oro circa +9% in
  EUR, contro −25% e −5% in USD); crypto prima del 2010 e `unknown` usano il proxy equity (flag
  `crypto_pre_inception_equity_proxy`, `unknown_asset_class_equity_proxy`); il max drawdown del
  metodo misto è approssimato; nessuna correlazione fra classi. Rimosso il vecchio
  `benchmark_drawdown × 0,8`.

## 2. Volatilità (due metriche, nessuna canonica — decisione TASK-37)

| Nome | Tool | Metodo | Periodo | Pavimento |
|---|---|---|---|---|
| `stress_portfolio_volatility` (= `portfolio_volatility_pct`) | `get_stress_test` | volatilità realizzata della serie ponderata del portafoglio (correlazioni incluse) | ultimo anno di chiusure giornaliere, annualizzata × √252 | sì: mai sotto la volatilità di lungo periodo del mix (16% equity, 6% bond, 15% commodity/oro, 0% cash); `is_floored`, `unfloored_pct` |
| `health_weighted_asset_volatility` (= `portfolio_volatility`) | `get_portfolio_health` | media ponderata delle volatilità dei singoli titoli, **senza correlazioni** (sovrastima il rischio di un portafoglio diversificato) | ultimo anno, almeno 20 rendimenti per titolo, rinormalizzata sul peso coperto | no |

## 3. Health score (`get_portfolio_health`, `_health.py`)

Score = somma dei punteggi di categoria; ogni categoria = massimo − punti tolti dalle regole
(`score_deductions`), limitata a [0, massimo].

| Categoria (max) | Regole (punti) |
|---|---|
| diversification (25) | USA > 60% (6); posizione > 40% (4); sovrapposizione > 50 (4); emergenti < 5% con azionario ≥ 60% (3) |
| risk (25) | volatilità health > 15% (10) oppure 12-15% (5); posizione > 40% (5) |
| concentration (20) | posizione > 60% (10) oppure > 40% (6); prime 3 > 75% (4) |
| overlap (15) | sovrapposizione > 70 (12), > 50 (8), > 40 (4) |
| cost_efficiency (15) | TER ponderato > 0,75% (10), > 0,5% (7), > 0,3% (3) |

**Limiti:** 100/100 è raggiungibile e significa solo che nessuna regola è scattata; le soglie sono
euristiche, non calibrate su dati; la volatilità usata è quella senza correlazioni; un TER `null`
non toglie punti.

## 4. Monte Carlo (`get_monte_carlo`, `_monte_carlo.py`)

- **Unità:** indice **base 100** (`unit: "indice_base_100"`, `initial_value: 100`): 120 = +20% sul
  valore attuale, non 120 €. Nessun versamento.
- **Rendimento atteso μ:** ipotesi di lungo periodo (nominali, EUR, composte) ponderate per classe:
  equity 6,5%, bond 3,0%, commodity/oro 3,5%, cash 2,0%; crypto e `unknown` → equity.
  Non si estrapola la performance recente.
- **Volatilità σ:** max(volatilità realizzata a 1 anno, volatilità di lungo periodo del mix con
  correlazioni equity-bond 0,1, equity-commodity 0,2, bond-commodity 0,2).
- **Distribuzione:** log-rendimenti annui con drift ln(1+μ) e shock Student-t (gradi di libertà
  stimati dalla curtosi, 3-30), riscalati per avere varianza σ²; 5.000 simulazioni, seed fisso 42.
- **Output MCP:** esattamente gli anni 1..10 con p25 ≤ p50 ≤ p75.
- **Limiti:** μ e correlazioni sono ipotesi fisse; senza storico prezzi la risposta è vuota;
  nessuna inflazione nell'indice (presente solo nel piano di decumulo).

## 5. TER e costi (`get_cost_breakdown`, `resolve_holding_ters` in `_health.py`)

- Fonte per posizione (`ter_source`): justETF (già in %) → yfinance `expense_ratio` normalizzato
  (0,0075 → 0,75%) → dedotto da pattern (`inferred`) → `none`.
- **Chiavi yFinance (TASK-52, `extract_expense_ratio_pct`)**: nell'ordine `netExpenseRatio` (chiave
  attuale, punti percentuali: 0,15 = 0,15%), `annualReportExpenseRatio` (frazione: 0,0015 = 0,15%) ed
  `expenseRatio` (storica); ogni valore passa da `normalize_expense_ratio_pct` (≤ 0,01 letto come
  frazione). Prima veniva letta solo `netExpenseRatio`/`expenseRatio`. `ProviderAssetInfo` riporta
  la chiave usata (`expense_ratio_source_key`). Per i metadati già salvati con la colonna
  `expense_ratio` vuota, `resolve_holding_ters` legge le stesse chiavi da `raw_info` (sola lettura,
  nessuna chiamata di rete). Un TER mancante resta `null` con `ter_source: "none"`: mai inventato.
- **Popolamento (azione del proprietario, API web autenticata)**: i metadati yFinance erano scritti
  solo aprendo la scheda di un titolo, da `reclassify-assets` o da `/assets/metadata/refresh-all`;
  gli ETF USA mai aperti (TLT, IEF, DJP, GLD) non avevano un `asset_metadata`, quindi nessun TER.
  `POST /api/portfolios/{id}/asset-metadata/backfill?limit=50` scarica i metadati degli asset del
  portafoglio senza riga `asset_metadata` e dei fondi/ETP (classificatore condiviso) senza expense
  ratio; risponde con `updated` (TER e chiave usata), `skipped`, `failed`.
  `POST /api/portfolios/{id}/etf-enrichment/backfill?refresh_missing_ter=true` riscarica da justETF
  anche le righe `etf_enrichment` già presenti ma senza TER (es. un ETC sull'oro tipizzato `stock`,
  che non viene saltato: si saltano solo `cash`, `crypto`, `bond`). Gli ETF USA non sono su justETF
  (ISIN US): per loro la fonte è yFinance.
- `weighted_ter_pct` = Σ(peso_i × TER_i) / Σ(peso_i coperti): **TER sul peso coperto** (decisione
  TASK-37). `ter_coverage_pct` = peso coperto / peso totale delle posizioni.
- `estimated_annual_cost_known_eur` e `fee_drag_10y_eur` sono calcolati sul solo
  `covered_market_value_eur` (stesso perimetro, `cost_perimeter`); `total_annual_cost_eur` è `null`
  quando la copertura è incompleta.
- I TER dedotti contano come coperti ma sono elencati in `inferred_ter_symbols`.
- **Limiti:** nessuna soglia minima di copertura (decisione aperta); commissioni di negoziazione,
  costi di transazione dei fondi e consulenza non inclusi.

## 6. Proiezione del reddito (`get_income_projection`) e dividendi (`get_dividend_summary`)

- Reddito lordo annuo = Σ valore_i × dividend_yield_i (yield da metadati Yahoo, in %), solo per le
  posizioni con yield > 0. **Solo distribuzioni**, non il rendimento totale: i fondi ad accumulazione
  non producono reddito e sono elencati in `missing_yield_symbols` (insieme a quelli senza dati).
- Bucket: `equity`, `fixed_income` (classe bond), `other_or_unknown` (oro, commodity, cash, crypto,
  `unknown`); la somma è il lordo proiettato. `unknown_class_symbols` elenca i non classificati.
- Crescita annua: equity 3%, reddito fisso 0% (anche bond indicizzati all'inflazione, decisione
  TASK-37), altro 0%. Proiezioni cumulate a 1, 3, 5 anni.
- Fiscalità: aliquota uniforme 26% (o `fire_capital_gains_tax_rate` dell'utente), dichiarata in
  `tax_note`. **Non modellati:** 12,5% sui titoli di Stato e quota governativa degli ETF, ritenute
  estere, imposta di bollo, plusvalenze.
- `yield_on_cost_pct` = reddito lordo / costo di carico.
- `get_dividend_summary` (TASK-44): dividendi incassati = Σ quantity × price delle transazioni
  `dividend` **per valuta** (`dividends_by_currency`); con più valute `mixed_currencies: true` e
  totali `null` (nessun helper FX nel tool); yield per posizione letto per asset_id.

## 7. Ribilanciamento (`calculate_rebalance_orders`, `services/rebalance.py`)

- Modalità: `rebalance` (predefinita: vendite che finanziano gli acquisti), `buy_only`, `sell_only`.
- Totale = valore delle posizioni **con un target** + liquidità del portafoglio + `available_cash`
  (liquidità **aggiuntiva**); i pesi includono la liquidità (decisioni TASK-37). Le posizioni senza
  target restano fuori dal totale e non vengono negoziate (`untargeted_holdings`).
- **Stessi pesi in scostamento e PAC (TASK-85, decisione del 2026-11-11):** `get_target_drift`,
  `calculate_pac_contribution` e lo scostamento dello snapshot del Copilot usano la stessa base
  (`current_target_weights` in `services/rebalance.py`, senza `available_cash`): peso attuale =
  valore dello strumento / (valore degli strumenti con target + liquidità attuale del modello della
  performance) × 100, dichiarato come `total_value`. Nel PAC il peso dopo il versamento è
  (valore + versamento) / (`total_value` + importo mensile). Il peso di `get_positions` (e
  `old_weight`/`new_weight` di `calculate_what_if`, che misurano la concentrazione) resta sul valore
  delle sole posizioni.
  Esempio, portafoglio 9101 del seed (70.000 / 20.000 / 10.000 €, liquidità 9.256,50, target
  50/40/10): 64,07 / 18,31 / 9,15 % in tutti e tre i tool, contro 70,0 / 20,0 / 10,0 % di prima in
  `get_target_drift` e nel PAC.
- **Tabella posizioni e what-if sulla stessa base (TASK-88):** la colonna Target della tabella
  posizioni legge `GET /portfolios/{id}/target-drift`, che usa la funzione di `get_target_drift`
  (`target_drift_rows`): stessi numeri del Copilot (9101: AUDTECH.DE −0,85 pt, prima «in linea» sul
  10,0 % fra le posizioni). Nella vista aggregata i target non esistono e la colonna non c'è.
  `calculate_what_if` calcola `old_drift`/`new_drift` con `current_target_weights` prima e dopo
  l'operazione, applicata al modello della liquidità: l'acquisto è pagato dalla liquidità del
  portafoglio (la parte oltre il saldo, che non scende sotto 0, entra nella base come nuovo
  versamento), la vendita lascia i proventi in liquidità. Così `old_drift` coincide con
  `get_target_drift` e `new_drift` è lo scostamento che `get_target_drift` mostrerebbe dopo aver
  registrato l'operazione; `target_basis` dichiara pesi, base e liquidità prima e dopo. Esempio
  9101, acquisto di 1.000 € di AUDEQ.MI: `old_drift` +14,07 (prima +20,0), `new_drift` +14,98
  (base invariata 109.256,50), `new_weight` 70,30 % fra le posizioni come prima.
- Banda di tolleranza 0,5 pp **come soglia di attivazione**: se almeno uno strumento supera la
  banda, tutti tornano al target.
- Ordine: prima le vendite, poi gli acquisti finanziati da liquidità + proventi; se non bastano,
  acquisti ridotti in proporzione.
- **Invariante:** `cash_after = cash_before + extra_cash + sells_eur − buys_eur ≥ 0`; risultato
  indipendente dall'ordine dei target. Nessun ordine minimo; commissioni e imposte non modellate.
- Limite: il route dell'app mantiene la semantica precedente (pesi sul solo investito, nessuna banda).
- **Anteprima REST del ribilanciamento non allineata (decisione TASK-88).** `POST
  /portfolios/{id}/rebalance/preview` resta sui pesi del valore investito (anche le posizioni senza
  target, liquidità esclusa), senza banda, con la sola liquidità che l'utente scrive in
  `cash_to_allocate`. Allinearla cambierebbe gli ordini in modo sorprendente: spenderebbe la
  liquidità del portafoglio senza che l'utente l'abbia indicata (e in `buy_only` la conterebbe due
  volte se l'utente la riscrive nel campo), ridimensionerebbe le vendite e aggiungerebbe acquisti.
  Esempio 9101 in modalità `rebalance` senza liquidità indicata: oggi vendita AUDEQ.MI 20.000 € e
  acquisto AUDBD.MI 20.000 €; sulla base comune vendita 15.371,75 €, acquisti AUDBD.MI 23.702,60 € e
  AUDTECH.DE 925,65 € (i 9.256,50 € di liquidità spesi). Conseguenza dichiarata: «Attuale %» e
  «Drift %» del modale dell'anteprima sono sul solo investito e possono differire dalla tabella
  posizioni e dal Copilot (9101: AUDTECH.DE 10,0 % / 0,0 contro 9,15 % / −0,85). Allinearla richiede
  una scelta di prodotto sul campo della liquidità (precompilato con il saldo?), fuori da TASK-88.

## 8. Performance (`get_performance`, `services/performance_service.py`)

- **TWR:** sotto-periodi delimitati dai giorni con flussi esterni;
  r_i = (V_fine − V_inizio − CF_giorno) / V_inizio, flusso a fine giornata; TWR = Π(1 + r_i) − 1.
  Annualizzato solo per periodi ≥ 365 giorni. Se il valore iniziale è 0 si parte dal primo flusso
  positivo; senza valore iniziale `twr_pct` è `null` (non 0).
- **MWR:** IRR (ACT/365) con valore iniziale come uscita, flussi invertiti (prospettiva investitore),
  valore finale come entrata; `mwr_pct` è il rendimento del periodo, l'annualizzato solo ≥ 1 anno.
- **Modello di liquidità (TASK-46, opzione A approvata):** la stessa regola vale per la serie
  dei valori V(t) (`repository/_transactions.py`, fold) e per i flussi esterni di TWR e MWR
  (`performance_service._get_cashflows_with_fallback`), perimetro singolo e aggregato; il codice è
  in `repository/_cash_model.py`.
  - acquisto: liquidità − (prezzo × quantità + commissioni + imposte), al cambio del giorno;
  - vendita: liquidità + (prezzo × quantità − commissioni − imposte); i proventi restano in
    liquidità (non sono un prelievo) finché non c'è un prelievo registrato;
  - deposito, interesse: +importo; dividendo: +(importo − `taxes`), cioè netto della ritenuta
    (TASK-47); prelievo, commissione (movimento `fee`): −importo (per questi lati `fees` non è
    applicato e `taxes` solo sui dividendi, come nel saldo di cassa del summary). La voce
    `dividend` di `get_external_cashflows` porta già l'importo netto.
- **Apporti impliciti:** la liquidità si chiude a fine giornata (tutti i movimenti del giorno,
  poi il saldo); se è negativa, lo scoperto è un **apporto esterno implicito** datato quel giorno
  (`implicit_contribution`) e la liquidità riparte da 0: non va mai sotto zero. Vale per un
  acquisto oltre la liquidità disponibile e, simmetricamente, per un prelievo o una commissione
  oltre la liquidità: la parte non coperta è denaro mai registrato in entrata, quindi il flusso
  netto del giorno è pari alla liquidità effettivamente uscita (il valore e i flussi restano
  coerenti, nessun rendimento fittizio). Il saldo all'inizio della finestra dipende da tutta la
  storia: il modello è ripiegato su tutte le transazioni fino alla fine della finestra (una sola
  lettura, in cache).
- **Flussi esterni:** depositi/prelievi registrati + apporti impliciti. Acquisti pagati con la
  liquidità e vendite spostano valore fra liquidità e titoli e non sono flussi. Dividendi,
  interessi e commissioni sono interni (rendimento). Il vecchio fallback "senza depositi usa
  acquisti/vendite" è un caso particolare: senza depositi ogni acquisto è interamente un apporto
  implicito (stessi flussi di prima); cambia solo il trattamento delle vendite, i cui proventi ora
  restano in liquidità a rendimento 0 invece di uscire come prelievo.
- **Valore V(t):** posizioni a prezzo di chiusura × FX + liquidità del modello sopra.
- **Riepilogo:** `total_deposits` = depositi + apporti impliciti della finestra;
  `implicit_contributions` (e `implicit_contributions_eur` per periodo in `get_performance`)
  espone la parte implicita. `cashflow_basis = 'trades'` quando la storia ha solo apporti impliciti.
- **Limiti:**
  - la liquidità storica è un unico saldo in valuta base (importi al cambio del giorno del
    movimento), non un saldo per valuta;
  - il saldo iniziale `portfolios.cash_balance` (senza data) è liquidità disponibile **prima della
    prima transazione** (TASK-49): entra nel fold il giorno della prima transazione (prima della
    chiusura di quel giorno) e, nei flussi, come `deposit` esterno di quel giorno (solo nella storia
    completa, cioè `get_external_cashflows` senza `start_date`, quella letta dalla performance).
    Prima di TASK-49 era escluso dalla serie storica;
  - dal TASK-49 `summary.cash_balance` è la fine di questo stesso fold (§9, §9.1): summary e serie
    storica non differiscono più;
  - l'ordine infragiornaliero non conta (chiusura a fine giornata): un deposito registrato dopo
    un acquisto nello stesso giorno lo copre;
  - le vendite oltre la quantità detenuta (bloccate in inserimento) azzerano la posizione ma
    accreditano l'intero controvalore, come la lista dei flussi.

## 9. Liquidità, prezzi e variazione giornaliera

- **Liquidità (TASK-47 + TASK-49, una sola regola, la stessa della performance):**
  `summary.cash_balance`, `GET /portfolios/{id}/cash-balance` (`total_cash`, sezione Cash del
  frontend), i tool copilot/MCP `get_cash_balance` / `get_portfolio_summary` /
  `get_aggregate_summary`, la lista dei portafogli (`current_cash_balance`), il valore intraday, il
  capitale iniziale del Monte Carlo e la liquidità disponibile del ribilanciamento usano lo stesso
  helper `_cash_balance_detail` (`repository/_utilities.py`), che ripiega **tutte** le transazioni
  con le regole di `_cash_model` (§8): saldo iniziale (liquidità prima della prima transazione) +
  depositi, interessi, dividendi **netti** e proventi netti delle vendite − prelievi, commissioni
  (`fee`) e acquisti (commissioni e imposte incluse); chiusura a fine giornata, scoperto = apporto
  implicito, liquidità mai negativa; data = `trade_at::date`. Espone anche
  `implicit_contributions_total` (summary, `GET /cash-balance`, tool MCP), la scomposizione
  `cash_breakdown` (saldo iniziale, depositi, prelievi, dividendi, interessi, commissioni, acquisti,
  vendite, apporti impliciti; somma = `total_cash`) e una `cash_model_note` in italiano. Una sola
  query sulle transazioni per l'insieme dei portafogli, fold O(n). Invariante: `market_value +
  cash_balance` del summary = ultimo valore della performance (`current_value`).
- **Cambio della liquidità in valuta estera:** ogni movimento non in valuta base è convertito al
  cambio **della sua data** (ultimo cambio disponibile ≤ data del movimento). È la regola del
  summary, del modello di liquidità della performance (TASK-46, §8) e del costo delle posizioni.
  Prima `total_cash` usava il cambio più recente sui saldi per valuta: i due numeri divergevano.
  Perché non il cambio corrente: il codice non tiene una liquidità in valuta estera come saldo
  autonomo (non esiste un'operazione di cambio valuta; un acquisto in USD non scala un saldo USD;
  il modello della performance tiene un unico saldo in valuta base), quindi ogni movimento è
  trattato come convertito in valuta base alla sua data. `currency_breakdown` di `get_cash_balance`
  resta un riepilogo **nominale** per valuta (senza conversione, saldo iniziale nella valuta
  base). Se il proprietario tiene davvero conti multi-valuta, la valutazione corretta di un saldo
  estero è al cambio corrente: richiederebbe saldi per valuta anche nel modello della performance
  (fuori perimetro; oggi tutti i movimenti sono in EUR).
- **Cambio mancante (non più silenzioso):** il calcolo non si interrompe (cambio 1,0) ma la valuta è
  riportata in `fx_missing_currencies` di `CashBalanceResponse` e di `PortfolioSummary` (quest'ultimo
  include anche le valute mancanti delle posizioni); un cambio esistente solo dopo la data del
  movimento conta come mancante.
- **Prezzo di mercato delle posizioni:** ultima chiusura giornaliera × FX della valuta di quotazione
  alla data del prezzo; `price_date` e `price_stale` esposti. Senza prezzo, o senza cambio della
  valuta di quotazione, il prezzo resta il costo medio (P/L 0) ma ora è segnalato:
  `Position.price_fallback = 'avg_cost'`, `Position.fx_missing` / `fx_missing_currencies` (anche per
  il cambio mancante di una transazione nel costo medio, convertita a 1,0);
  `PortfolioSummary.price_fallback_symbols`. I tool `get_positions`, `get_portfolio_summary`,
  `get_cash_balance` (e gli aggregati `get_aggregate_summary` / `get_aggregate_positions`) espongono
  i campi e una `data_quality_note` in italiano solo quando c'è qualcosa da segnalare.
  `quote_currency` dei listing `.L` da riconciliare (TASK-41).
- **Freschezza dei prezzi e barre giornaliere (TASK-53):**
  - *Da dove arriva il prezzo:* `market_price` e `price_date` vengono dall'ultima barra di
    `price_bars_1d`; i `price_ticks` servono alla variazione giornaliera. Le barre erano scritte solo
    da backfill manuali (`backfill_daily` dopo il refresh dalla UI), nuove transazioni o pagina
    dell'asset; il job delle 06:30 copre solo i benchmark.
  - *Job giornaliero delle barre:* `daily_bars` (APScheduler, lun-ven alle
    `DAILY_BARS_SCHEDULER_HOUR:MINUTE` UTC, default 22:30) scarica gli ultimi
    `DAILY_BARS_LOOKBACK_DAYS` (default 10) giorni di calendario, seduta del giorno compresa, per
    **tutti gli asset attivi in un qualsiasi portafoglio** (transazioni o target), con
    `price_backfill_max_workers` richieste in parallelo e nessuna connessione DB tenuta durante le
    chiamate (due letture brevi prima, una scrittura breve per asset). Simbolo: listing mappato in
    `asset_provider_symbols` (lo stesso con cui sono scritte le barre esistenti), poi simbolo, poi
    ISIN; fallback per ISIN se lo storico è insufficiente, come `backfill_daily`. Acceso da
    `DAILY_BARS_SCHEDULER_ENABLED` (non impostato = segue `PRICE_SCHEDULER_ENABLED`). Log di sintesi
    `Daily bars job completed ... updated/no_new_bar/lagging/failed ... lagging_symbols=...`.
  - *Righe Yahoo incomplete (causa di XAD1.DE):* il client scartava in silenzio le sedute con
    chiusura ma `open/high/low` o `adjclose` nulli (comportamento ereditato da yfinance): per un
    listing poco scambiato lo storico si fermava all'ultimo giorno "completo" senza errori. Ora la
    riga è tenuta, i valori mancanti presi dalla chiusura (log `daily_bars_partial_rows`); le righe
    senza chiusura restano scartate ma loggate (`daily_bars_rows_without_close`).
  - *Log per asset dei backfill* (`backfill_daily`, `backfill_single_asset`, job giornaliero): barre
    scartate dalla validazione (`daily_bars_rejected`, motivo nelle righe `price_bar_rejected`) e
    nessuna barra nuova quando la borsa dell'asset ha chiuso almeno una seduta dopo l'ultima barra
    (`daily_bars_no_new_bar ... last_bar=... missed_sessions=... reason=...`); "niente di nuovo" in
    regola resta a debug.
  - *Quotazione ferma:* `price_stale` non usa più i 5 giorni di calendario ma il calendario della
    borsa dell'asset (`services/market_hours.py`: orari dal suffisso del simbolo mappato, weekend e
    principali festività NYSE/europee, crypto 7/7, cambi 5/7, ISIN/sconosciuti giorni feriali): il
    prezzo è fermo quando dopo `price_date` si sono **concluse** almeno `PRICE_STALE_MAX_SESSIONS`
    (default 2) sedute. Esempio: barra di venerdì → lunedì sera 1 seduta, non stale; XAD1.DE con
    barra del 30/10 → il 3/11 dopo la chiusura Xetra "ultima quotazione del 30/10, 2 sedute fa".
    Calcolato in lettura, quindi funziona anche senza scheduler. Campi additivi:
    `Position.stale_reason`, `Position.last_price_at` (ultimo tick del provider),
    `PortfolioSummary.stale_price_symbols`; tool `get_positions` (`price_date`, `price_stale`,
    `stale_reason`, `last_price_at` e nota), `get_portfolio_summary`/`get_aggregate_summary`
    (`stale_price_symbols` e nota), `get_day_movers` (`stale_positions` con motivo).
  - *Timestamp del provider ripetuto:* il tick usa il timestamp di mercato del provider, quindi una
    quotazione ferma riscrive la stessa chiave `(asset, provider, ts)` senza lasciare traccia. Il
    refresh confronta il ts della quotazione con l'ultimo tick salvato: se non è più recente a
    borsa aperta, o per `PRICE_UNCHANGED_TS_WARN_AFTER` (default 3) refresh di fila, logga
    `price_unchanged_ts ... symbol=... ts=... stored_ts=... source=...` (una volta per asset al
    giorno) e lo riporta in `PriceRefreshResponse.unchanged_ts_symbols`. Upsert invariato.
  - *Sincronizzazione e freschezza globale (TASK-54):* quotazioni, barre e cambi arrivano da
    un'unica procedura con lock (trigger esterno GitHub Actions, recupero all'avvio, scheduler);
    `last_successful_price_sync` avanza solo se ogni asset ha la barra dell'ultima seduta conclusa
    della sua borsa (stessi calendari). I tool con valori riportano `data_freshness` e
    `get_data_freshness` il dettaglio per posizione: vedi `docs/market-data-sync.md`.
- **Ritenute sui dividendi (decisione TASK-47):** la liquidità riceve il dividendo **netto**
  (`quantity × price − taxes`) nel summary, in `get_cash_balance` (totale e `currency_breakdown`), nel
  `cash-flow-timeline` e nel modello di liquidità della performance (§8). `get_dividend_summary`
  continua a riportare i dividendi **lordi** (analisi del reddito). Con i dati attuali (ritenute a
  0) nessun numero cambia.
- **Variazione giornaliera della posizione:** (ultimo prezzo / chiusura precedente − 1) × 100 in
  **valuta di quotazione** (senza FX), arrotondata a 2 decimali; chiusura precedente dal tick Yahoo,
  altrimenti penultima barra giornaliera. `previous_close_available` (TASK-44) dice se esiste.
- **Variazione del summary:** Σ q_i × (prezzo_i × FX_corrente − chiusura_prec_i × FX_prec), prezzi
  non arrotondati; `day_change_pct` = variazione / valore precedente delle posizioni (liquidità
  esclusa); un prezzo vecchio di oltre 7 giorni contribuisce 0 ma resta nel denominatore. La somma
  delle percentuali arrotondate delle posizioni non ricostruisce il summary (atteso).
- **Perimetro di `day_change_pct` (decisione TASK-86):** il denominatore è **sempre tutto il
  valore investito** (liquidità esclusa). Ogni posizione vi entra: con una variazione misurabile
  col suo valore alla chiusura precedente (q × chiusura_prec × FX_prec); con un prezzo vecchio di
  oltre 7 giorni con lo stesso valore precedente e contributo 0; **senza variazione misurabile**
  (nessuna chiusura precedente: una sola barra e nessun tick; barre dello stesso giorno; metadati,
  cambio o prezzo non validi) col suo `market_value` corrente e contributo 0. Prima di TASK-86
  queste ultime uscivano anche dal denominatore e la percentuale si gonfiava (seed dell'Auditor,
  9107: −0,13% invece di −0,09%; aggregato −0,13% invece di −0,12%). È la stessa definizione di
  `get_day_movers` (§11) letta da un altro lato: le quotazioni ferme e senza chiusura precedente non
  hanno una variazione del giorno (fuori dalla classifica migliori/peggiori, contributo 0 al
  riepilogo) ma restano posizioni del portafoglio (contate in `excluded_*`, valore nel
  denominatore). Così la percentuale è «variazione di oggi / valore del portafoglio» per tutti i
  consumatori: Dashboard (KPI «Oggi», hero mobile, griglia dell'analisi mostrano
  `summary.day_change_pct` senza ricalcolarla), tool Copilot/MCP `get_portfolio_summary` e
  `get_aggregate_summary`, export Markdown; lo snapshot aggregato del Copilot
  (`copilot/snapshot.py`) usa già `day_change / (market_value − day_change)`, che conta tutte le
  posizioni. `day_change` (importo) non cambia. Verifica: regola dell'Auditor
  C-DAYCHANGE-DENOMINATOR (`docs/auditor/rules.md`).
- **Quantità:** nessun arrotondamento all'origine; output arrotondato a 8 decimali; nessuna
  tolleranza contabile (un residuo resta una posizione). Costo medio ponderato (non FIFO).

### 9.1 Liquidità del summary vs modello della performance (TASK-47 → decisione TASK-49)

**Decisione applicata (TASK-49, 2026-11-03): opzione 1.** Il summary adotta il modello di liquidità
della performance (una sola verità, §9). Dettagli dell'implementazione:
- `_cash_balance_detail` ripiega tutte le transazioni con `_cash_model.cash_delta` / `fold_cash`
  (cambio della data del movimento, chiusura a fine giornata, liquidità mai negativa);
- **saldo iniziale:** `portfolios.cash_balance` non ha data ed è trattato come liquidità disponibile
  prima della prima transazione, in modo identico nella liquidità corrente e nella storia della
  performance (il fold dei valori parte da quel saldo il giorno della prima transazione; i flussi
  esterni lo contano come `deposit` di quel giorno, quindi è capitale versato e non rendimento). Un
  portafoglio senza transazioni ha come liquidità il solo saldo iniziale. Modificare il saldo
  iniziale (PATCH del portafoglio) cambia retroattivamente la storia;
- `implicit_contributions_total` dice da dove è venuto il denaro degli acquisti non coperti dalla
  liquidità registrata (portafogli di sole operazioni: ogni acquisto oltre i proventi delle vendite);
- invariato: nessuna migrazione dello schema; `cash-flow-timeline` (`cumulative_cash`) resta il
  cumulato dei soli movimenti di cassa (non usato dal frontend).

Esempio sintetico qui sotto dopo TASK-49: liquidità 544,80, totale del summary 1094,80 = valore della
performance (`tests/unit/test_cash_model_task49.py`); portafoglio di sole operazioni (acquisto
10 × 100, vendita 4 × 110, acquisto 1 × 110, prezzo 110): liquidità 330, apporti impliciti 1000,
totale 1100 = valore della performance.

Analisi originale (TASK-47), che descrive lo stato **prima** di TASK-49:

**Come era calcolato `summary.cash_balance` prima di TASK-49.** `SummaryMixin.get_summary` →
`get_current_cash_balance_detail` → `_cash_balance_detail`: saldo iniziale della colonna
`portfolios.cash_balance` + depositi + interessi + dividendi netti − prelievi − commissioni `fee`.
Acquisti e vendite sono **ignorati**, e non c'è alcun meccanismo che li compensi:
- `create_transaction` (`repository/_transactions.py`) inserisce solo la riga: non aggiorna
  `portfolios.cash_balance` e non genera prelievi/depositi automatici; lo stesso vale per gli
  acquisti del PAC (`routes_pac.py`), per il commit del ribilanciamento (`routes_rebalancing.py`) e
  per l'import CSV (solo le righe del file);
- `portfolios.cash_balance` cambia solo alla creazione o con la modifica manuale del portafoglio
  (`_portfolio_crud.py`, PATCH); non ha data;
- i movimenti di cassa arrivano da `POST /cash-movements` (sezione Cash) o dall'import CSV.

Il frontend mostra `total_cash` nella sezione Cash, `summary.cash_balance` nella Panoramica e nel
selettore dei portafogli, e somma `market_value + cash_balance` come valore totale (hero mobile,
vista aggregata); Monte Carlo usa lo stesso totale come capitale iniziale, il ribilanciamento
copilot usa `cash_balance` come liquidità disponibile.

La performance (TASK-46, §8) usa invece il modello di liquidità: acquisti pagati dalla liquidità,
proventi delle vendite in liquidità, scoperto = apporto implicito, saldo iniziale escluso.

**Esempio sintetico** (EUR, saldo iniziale 0, prezzo finale 110):

| Movimento | Summary: liquidità | Modello performance: liquidità |
|---|---|---|
| g1 deposito 1000 | 1000 | 1000 |
| g2 acquisto 8 × 100 | 1000 (ignorato) | 200 |
| g3 vendita 3 × 110 | 1000 (ignorata) | 530 |
| g4 dividendo 20, ritenuta 5,20 | 1014,80 | 544,80 |
| **Valore totale** (5 titoli × 110 = 550 + liquidità) | **1564,80** | **1094,80** |

Il valore reale è 1094,80 (1000 versati + 80 di plusvalenza + 14,80 di dividendo netto): il
summary conta due volte gli 800 investiti e non vede i 330 incassati (scarto = acquisti − vendite =
470). Senza depositi registrati (portafogli di sole operazioni, come quelli del proprietario):
acquisto 10 × 100, vendita 4 × 110 → summary: liquidità 0, totale 660; performance: liquidità 440
(i 1000 dell'acquisto sono un apporto implicito), valore 1100 — la performance supera il summary
dei proventi delle vendite, come annotato in TASK-46.

**Opzioni (decisa e implementata la 1 in TASK-49):**

1. **Il summary adotta il modello della performance** (stessa funzione di `_cash_model`: acquisti −,
   vendite +, scoperto a 0 come apporto implicito; il saldo iniziale come deposito alla data di
   creazione del portafoglio). *Pro:* una sola liquidità ovunque, totale del summary = ultimo
   valore della performance, niente doppio conteggio nel totale, Monte Carlo e ribilanciamento.
   *Contro:* cambia la liquidità mostrata di ogni portafoglio con acquisti/vendite (con depositi:
   cala degli acquisti netti; senza depositi: compaiono i proventi delle vendite); chi ha usato
   `cash_balance` come saldo reale aggiornato a mano vedrebbe gli acquisti scalati due volte.
   *Dati:* nessuna migrazione dello schema; ricalcolo puro, da verificare portafoglio per
   portafoglio con le query in sola lettura prima del rilascio.
2. **Due grandezze esplicite** (nessun numero esistente cambia): `cash_balance` resta il "saldo dei
   movimenti di cassa" ed è etichettato così in UI e MCP; si aggiunge `cash_balance_model` (liquidità
   del modello della performance) e `total_value` = `market_value + cash_balance_model`, usato per
   i totali del frontend, Monte Carlo e ribilanciamento. *Pro:* additivo, reversibile, trasparente.
   *Contro:* due numeri di liquidità da spiegare; finché i totali usano `cash_balance` il doppio
   conteggio resta. *Dati:* nessun impatto.
3. **La performance torna alla semantica del summary** (liquidità solo dai movimenti di cassa,
   acquisti/vendite come flussi esterni). *Pro:* summary invariato. *Contro:* reintroduce
   l'errore C1-TWR-MIXED corretto in TASK-46 (con depositi e acquisti nello stesso periodo il
   capitale è contato due volte); sconsigliata. *Dati:* nessuno.

Raccomandazione tecnica: opzione 1 (eventualmente preceduta dalla 2 come passaggio di
transizione per confrontare i due valori sui dati reali).

## 10. Classificazione delle asset class (`services/asset_classification.py`)

Ordine (vince la prima regola), con la fonte riportata in `source`: (1) `asset_type` già di classe
(cash, bond, crypto) → `asset_type`; (2) dati ETF strutturati: justETF `investment_focus`/
`index_tracked` e yfinance `category` → `enrichment`, poi il nome ufficiale salvato da justETF per
l'ISIN (`etf_enrichment.name`) → `enrichment_name`; (3) parole chiave nel nome → `name`;
(4) abbreviazioni del broker (TASK-50) → `name_abbrev`; (5) simbolo/ISIN noti → `symbol`/`isin`;
(6) `stock` → equity (`default`), salvo nomi da ETP (ETC/ETN/ETF) → `unknown`; ogni altro
tipo → `unknown`.

**Abbreviazioni del broker (TASK-50, fallback motivato).** I nomi importati da Fineco sono codici
brevi (`XTR2 EGB13 1CC` = Xtrackers Euro Government Bond 1-3, `Azioni Europa`). Due tabelle
esplicite in `asset_classification.py`, solo token interi (confini di parola):
`_BOND_ABBREVIATIONS` (EGB/EGBnn, EUR GOV/GOVT, GOV/GOVT BD, GOV, govies, TREAS/TRSY/TSY, CORP BD,
BD, AGG, obbl/obblig*, titoli di stato, INFL, BUND, T-BILL) e `_EQUITY_ABBREVIATIONS` (azioni,
azion*, EQ/EQU, WRLD/WLD, SP500, STX, SHS). Se il nome contiene segnali di entrambe le classi resta
`unknown`; parole solo geografiche ("Europa", "Europe") non sono segnali. Come per le parole chiave,
il nome di un asset `stock` non è letto (salvo che dica ETC/ETN/ETF): "Barrick Gold" e "Treasury
Wine" restano equity.

**Dati che arrivano al classificatore.** Holdings del Doctor (stress, salute, X-Ray, Monte Carlo) e
proiezione del reddito leggono con una sola query (`load_classification_inputs` in `_holdings.py`)
`asset_type`, ISIN, `asset_metadata.category` e da `etf_enrichment` `investment_focus`,
`index_tracked` e `name`. Prima del TASK-50 il reddito non riceveva ISIN, `index_tracked` né il nome
justETF. L'analizzatore pubblico passa l'ISIN del catalogo. Nessuna lettura chiama provider esterni.

**Arricchimento mancante.** Le analisi e l'MCP non scaricano dati (sola lettura). Per popolare
`etf_enrichment` degli asset di un portafoglio che ne sono privi: `POST
/api/portfolios/{id}/etf-enrichment/backfill` (stesso percorso di `POST
/api/assets/{id}/etf-enrichment/refresh`, che resta per un singolo asset); salta cash/crypto/bond
diretti e asset senza ISIN e riporta `enriched`/`skipped`/`failed`. L'X-Ray web lo fa da solo solo
con `JUSTETF_XRAY_AUTO_ENRICH_ENABLED` (default: solo in dev); non c'è un job schedulato.

**`instrument_type` (TASK-51).** Veicolo, distinto dalla classe: `etc` (token ETC, Xetra-Gold o ISIN
noto di ETC fisico sull'oro), `etn` (token ETN), `etf`/`fund` (tipo salvato, o `stock` con nome da
ETF/UCITS), `stock`, `bond`, `crypto`, `cash`; `null` se non determinabile. `search_asset_info`
espone `type` (tipo tecnico salvato), `asset_class`, `instrument_type`, `classification_source` e una
nota: per allocazione e rischio si usa `asset_class`. Classi: equity, bond, gold, commodity, cash, crypto, unknown. `unknown` non diventa
mai equity nel classificatore: ogni consumatore lo dichiara (flag/bucket). Il refresh prezzi non
cambia un etf/fund in stock né in bond (TASK-44). Schema invariato (ETC restano `etf`/`stock`).

## 11. Day movers (`get_day_movers`)

Fonte: `get_positions`. Escluse le posizioni con prezzo stale o assente (`excluded_stale`; da
TASK-53 elencate in `stale_positions` con `price_date` e `stale_reason`) e quelle
senza chiusura precedente (`excluded_no_previous_close`). Migliore/peggiore per `day_change_pct`,
parità risolte in ordine alfabetico del simbolo; senza posizioni valide `best`/`worst` = `null` con
`reason`. La variazione è in valuta di quotazione (senza effetto cambio).

## 12. X-Ray (`get_xray_summary`, `_xray.py`)

- Look-through: top holdings justETF, altrimenti yfinance; oro/commodity/crypto/monetario senza
  look-through (nessuna chiamata Yahoo), obbligazioni senza chiamata Yahoo.
- **Stato per posizione (TASK-52)**: `lookthrough_status` + `lookthrough_reason` (italiano) in
  `etf_details` e `coverage_issues`:
  - `not_applicable`: oro, materie prime, cripto, monetario e **obbligazioni**. Lo X-Ray è un
    look-through **azionario** (titoli, paesi e settori delle azioni): un fondo obbligazionario
    detiene obbligazioni, non azioni, e il look-through dei titoli obbligazionari non è modellato
    (le eventuali top holdings justETF di un fondo obbligazionario restano visibili ma non entrano
    nella copertura applicabile).
  - `missing`: fondo azionario o strumento `unknown` senza top holdings (nessun arricchimento justETF
    salvato e Yahoo senza dati, oppure errore temporaneo di Yahoo).
  - `available`: top holdings note, oppure titolo singolo (sottostante di sé stesso).
- `applicable_lookthrough_coverage_pct` = Σ quota scomposta delle posizioni applicabili (come in
  `lookthrough_coverage_pct`) / Σ quote delle posizioni applicabili (`available` + `missing`) × 100;
  `null` se nessuna posizione è applicabile. Denominatore dichiarato in `applicable_denominator`.
  `available_pct`, `not_applicable_pct`, `missing_pct` = quote del `coverage_denominator` per stato
  (sommano a 100). Esempio All Weather (TLT 40, IEF 15, VTI 30 con top 10 al 30%, DJP 7,5, GLD 7,5):
  `not_applicable_pct` 70, applicabile = VTI, `applicable_lookthrough_coverage_pct` 30, contro un
  `lookthrough_coverage_pct` del 9%. `coverage_note` apre con questa frase ("Scomposto il X% della
  parte azionaria; Y% del portafoglio non applicabile (oro, obbligazioni…); Z% con dati mancanti").
- **Yahoo (TASK-52)**: `get_etf_top_holdings` restituisce `[]` solo quando Yahoo dichiara che non ci
  sono dati di fondo (`YFDataException`, es. un'azione) — risposta memorizzata 1 h; un errore di rete
  o di rate limit solleva `ProviderError` e **non** è memorizzato (prima diventava "nessuna holding"
  per un'ora: plausibile causa dello 0% di VTI in All Weather). I pesi Yahoo sono frazioni del fondo
  (0,065 = 6,5%), convertiti correttamente (nessun errore di unità trovato); le top 10 di VTI coprono
  circa un terzo del fondo, compatibile con il 14,2% di 100% Azionario (solo VTI scomposto). VEUR/VFEM (UCITS irlandesi) non hanno top holdings su Yahoo: senza
  `etf_enrichment` (justETF, ISIN IE…) sono `missing` — limite del provider, si risolve con
  `POST /api/portfolios/{id}/etf-enrichment/backfill` (l'MCP non scarica nulla).
- **Denominatore unico (TASK-48, `coverage_denominator`)**: valore di mercato delle posizioni,
  liquidità esclusa (il saldo di cassa non è una posizione; escluse anche le posizioni di tipo
  `cash`). Quota di una posizione = peso / Σ pesi delle posizioni non cash × 100.
- `lookthrough_coverage_pct` = Σ_fondi quota_fondo × min(Σ pesi delle top holdings elencate, 100) / 100
  \+ Σ quote dei titoli singoli (un'azione è già il proprio sottostante). Esempio: fondo al 50% con
  top 10 che sommano al 45% → contribuisce 22,5%. Per fondo: `listed_holdings_pct`.
- `funds_with_holdings_pct` = Σ quote delle posizioni con almeno una top holding: è ciò che
  misurava `coverage_pct`, che resta invariato (stesso numeratore, denominatore = tutte le posizioni;
  coincidono senza posizioni di tipo `cash`). Misura la presenza di dati, non la profondità.
- Esposizioni geografiche/settoriali (`aggregated_country_exposure`, `aggregated_sector_exposure`):
  in % del denominatore, **sommano a 100** (2 decimali, residuo di arrotondamento sul bucket
  maggiore). Per ogni posizione: pesi justETF del fondo (o paese/settore dei metadati yFinance per un
  titolo singolo); la parte non elencata (pesi < 100) va in **"Non classificato"**, pesi > 100 sono
  riscalati; senza dati la posizione intera va nel bucket della sua asset class (classificatore
  condiviso: "Oro (asset class)", "Obbligazioni (asset class)", "Materie prime (asset class)",
  "Cripto (asset class)", "Monetario (asset class)") oppure in "Non classificato" (azionario o
  `unknown`). Etichette del provider (es. "Other") restano come sono.
- `classified_country_pct` / `classified_sector_pct` = quota con un paese/settore nominato (esclusi
  "Non classificato" e i bucket di asset class); `unclassified_*_pct` = bucket "Non classificato".
- Peso aggregato di un titolo = Σ peso_fondo × peso_nel_fondo, sul totale delle posizioni (invariato).
- **Data di riferimento**: per posizione `data_source` (`justetf`/`yahoo`/`none`), `data_as_of` e
  `data_as_of_basis`: `holdings_date` dichiarata da justETF se leggibile, altrimenti `fetched_at` del
  profilo in `etf_enrichment`; per Yahoo (nessuna data del provider) l'ora del download nella cache
  in memoria (`fetch_time`, TTL 1 h). `data_as_of` complessivo = la data più vecchia.
- `coverage_note` in italiano riassume le tre misure e la data. Copilot/MCP: esposizioni troncate
  ai primi 10 bucket + "Altri" + "Non classificato" (sommano sempre a 100), `funds` (max 20) con
  fonte, data, `lookthrough_status`/`lookthrough_reason`, 5 `coverage_issues` (prima i `missing`,
  ognuno con `lookthrough_status`) + `coverage_issues_total`; in più
  `applicable_lookthrough_coverage_pct`, `applicable_denominator`, `available_pct`,
  `not_applicable_pct`, `missing_pct`.
- Limiti: i titoli singoli restano elencati fra le `coverage_issues` (yfinance non restituisce
  holdings) e non entrano negli `aggregated_holdings`.

## 13. Tool aggregati MCP (`get_aggregate_*`)

`portfolio_ids` 2-20 id unici, stessa valuta base, ogni id autorizzato con `resolve_portfolio_scope`
(errore unico "Portfolio non trovato"). Valori come le route aggregate dell'app: posizioni dello
stesso asset unite, flussi per portafoglio (un trasferimento fra portafogli selezionati si annulla).
Sola lettura. Non esistono aggregati per drift, ribilanciamento, what-if, PAC, dividendi, costi,
reddito, day movers.

## 14. Limiti operativi MCP (`mcp_server/tools.py`, `config.py`)

| Limite | Valore predefinito |
|---|---|
| Richieste per utente | 60 ogni 60 s (`mcp_rate_limit_*`) |
| Tool pesanti (Monte Carlo, stress, reddito, X-Ray, ribilanciamento, what-if, PAC, aggregati pesanti) | 10 ogni 60 s (`mcp_heavy_tool_rate_limit_*`) |
| Chiamate concorrenti per utente | 4 (`code: concurrency_busy`, `retry_after_s: 2`) |
| Timeout per chiamata | 20 s |
| Dimensione del risultato | 200 KB, poi troncato con marcatore |
| Risultati | `get_positions` max 30, `get_recent_transactions` max 20 |

La concorrenza è verificata prima della quota pesante; gli errori di limite hanno
`structuredContent {code, message, retry_after_s}`. I limiti sono in memoria, per processo.
