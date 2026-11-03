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
- Totale = valore delle posizioni + liquidità del portafoglio + `available_cash` (liquidità
  **aggiuntiva**); i pesi includono la liquidità (decisioni TASK-37).
- Banda di tolleranza 0,5 pp **come soglia di attivazione**: se almeno uno strumento supera la
  banda, tutti tornano al target.
- Ordine: prima le vendite, poi gli acquisti finanziati da liquidità + proventi; se non bastano,
  acquisti ridotti in proporzione.
- **Invariante:** `cash_after = cash_before + extra_cash + sells_eur − buys_eur ≥ 0`; risultato
  indipendente dall'ordine dei target. Nessun ordine minimo; commissioni e imposte non modellate.
- Limite: il route dell'app mantiene la semantica precedente (pesi sul solo investito, nessuna banda).

## 8. Performance (`get_performance`, `services/performance_service.py`)

- **TWR:** sotto-periodi delimitati dai giorni con flussi esterni;
  r_i = (V_fine − V_inizio − CF_giorno) / V_inizio, flusso a fine giornata; TWR = Π(1 + r_i) − 1.
  Annualizzato solo per periodi ≥ 365 giorni. Se il valore iniziale è 0 si parte dal primo flusso
  positivo; senza valore iniziale `twr_pct` è `null` (non 0).
- **MWR:** IRR (ACT/365) con valore iniziale come uscita, flussi invertiti (prospettiva investitore),
  valore finale come entrata; `mwr_pct` è il rendimento del periodo, l'annualizzato solo ≥ 1 anno.
- **Flussi esterni:** depositi/prelievi; se nella finestra non ce ne sono, acquisti (costo +
  commissioni) e vendite (proventi − commissioni). Dividendi, interessi e commissioni sono interni.
- **Valore V(t):** posizioni a prezzo di chiusura × FX + liquidità = depositi − prelievi +
  dividendi + interessi − commissioni (gli acquisti **non** riducono la liquidità).
- **Limite (issue aperta C1-TWR-MIXED):** con depositi e acquisti nella stessa finestra l'acquisto
  è contato come rendimento (vedi [audit-findings.md](audit-findings.md)).

## 9. Liquidità, prezzi e variazione giornaliera

- **Liquidità:** deposito/interessi/dividendi +, prelievo/commissione −, buy/sell ignorati; data =
  `trade_at::date`; FX alla data del movimento in `summary.cash_balance`, FX più recente in
  `get_cash_balance.total_cash` (issue aperta C2-CASH-FX); FX mancante → 1,0.
- **Prezzo di mercato delle posizioni:** ultima chiusura giornaliera × FX della valuta di quotazione
  alla data del prezzo; `price_date` e `price_stale` esposti. Senza FX il prezzo resta il costo
  medio (issue aperta C4-FX-FALLBACK). `quote_currency` dei listing `.L` da riconciliare (TASK-41).
- **Variazione giornaliera della posizione:** (ultimo prezzo / chiusura precedente − 1) × 100 in
  **valuta di quotazione** (senza FX), arrotondata a 2 decimali; chiusura precedente dal tick Yahoo,
  altrimenti penultima barra giornaliera. `previous_close_available` (TASK-44) dice se esiste.
- **Variazione del summary:** Σ q_i × (prezzo_i × FX_corrente − chiusura_prec_i × FX_prec), prezzi
  non arrotondati; `day_change_pct` = variazione / valore precedente delle posizioni (liquidità
  esclusa); un prezzo vecchio di oltre 7 giorni contribuisce 0 ma resta nel denominatore. La somma
  delle percentuali arrotondate delle posizioni non ricostruisce il summary (atteso).
- **Quantità:** nessun arrotondamento all'origine; output arrotondato a 8 decimali; nessuna
  tolleranza contabile (un residuo resta una posizione). Costo medio ponderato (non FIFO).

## 10. Classificazione delle asset class (`services/asset_classification.py`)

Ordine (vince la prima regola): (1) `asset_type` già di classe (cash, bond, crypto); (2) dati ETF
(justETF `investment_focus`/`index_tracked`, yfinance `category`); (3) parole chiave nel nome;
(4) simbolo/ISIN noti; (5) `stock` → equity, salvo nomi da ETP (ETC/ETN/ETF) → `unknown`; ogni altro
tipo → `unknown`. Classi: equity, bond, gold, commodity, cash, crypto, unknown. `unknown` non diventa
mai equity nel classificatore: ogni consumatore lo dichiara (flag/bucket). Il refresh prezzi non
cambia un etf/fund in stock né in bond (TASK-44). Schema invariato (ETC restano `etf`/`stock`).

## 11. Day movers (`get_day_movers`)

Fonte: `get_positions`. Escluse le posizioni con prezzo stale o assente (`excluded_stale`) e quelle
senza chiusura precedente (`excluded_no_previous_close`). Migliore/peggiore per `day_change_pct`,
parità risolte in ordine alfabetico del simbolo; senza posizioni valide `best`/`worst` = `null` con
`reason`. La variazione è in valuta di quotazione (senza effetto cambio).

## 12. X-Ray (`get_xray_summary`, `_xray.py`)

- Look-through: top holdings justETF, altrimenti yfinance; oro/commodity/crypto senza look-through.
- `coverage_pct` = peso delle posizioni con almeno una top holding / peso totale delle posizioni
  (liquidità esclusa). Misura la presenza di dati, **non** la profondità del look-through (le top 10
  possono coprire il 20% del fondo) né la qualità della diversificazione.
- Peso aggregato di un titolo = Σ peso_fondo × peso_nel_fondo, sul **totale** del portafoglio.
- Esposizioni geografiche/settoriali: solo da justETF, sul totale (non sommano a 100).
- Limiti: nessuna data di riferimento dei dati del provider; solo 5 `coverage_issues` nel tool MCP
  (issue aperta C6).

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
