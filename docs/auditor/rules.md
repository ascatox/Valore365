# Auditor dei calcoli — Catalogo delle regole

Contratto delle regole implementate da TASK-74 (gruppo A), TASK-75 (B), TASK-76 (C) e TASK-77 (D).
Interfaccia, esiti, codici e contesto: `docs/auditor/architecture.md`. Portafogli di prova: §1
(contratto per TASK-78). Origine dei finding: `docs/audit-mcp-2026-11/audit-findings.md`.

Ogni condizione usa **i nomi reali dei campi** dell'output dei tool (`src/backend/app/copilot_tools.py`,
`src/backend/app/mcp_server/aggregate_tools.py`, `src/backend/app/copilot_doctor_tools.py`), dopo
`sanitize_output`. Gli id, i titoli, le severità, gli scope e le tolleranze di questo catalogo sono
vincolanti: le dichiarazioni `RULES` li copiano esattamente.

Totale: **52 regole** — A 11, B 10, C 11, D 20.

## 0. Convenzioni

### 0.1 Come leggere una scheda

- **Titolo**: testo per l'utente (TASK-81), sobrio, senza id né gergo.
- **Sev. / Area / Finding / Scope**: campi della dichiarazione («—» nei finding = lista vuota:
  proprietà di conservazione o di coerenza senza un finding di origine).
- **Tool**: tool e argomenti (canonici, architettura §5.2). `scoped(T)` = `ctx.scoped(T, scope)`;
  per lo scope `aggregate` diventa il `get_aggregate_*` corrispondente.
- **Condizione**: la regola è `pass` se **tutte** le verifiche elencate reggono, `fail` alla prima
  (o a tutte: le evidenze possono elencare ogni violazione, massimo 50) che non regge.
- **Tolleranze**: assolute, nell'unità del campo, con il motivo in §0.2.
- **Skip**: unici casi in cui la regola non giudica; ogni altro caso è `pass` o `fail`.
- **Prova**: portafogli di §1 su cui la regola deve essere valutata (non `skip`) sul codice corretto.
- **Difetto**: cosa il test unitario reintroduce per vederla fallire.

### 0.2 Tolleranze e loro motivo

Le tolleranze compensano **solo** gli arrotondamenti che i tool fanno davvero; non assorbono
differenze di metodo. n = numero di elementi sommati.

| simbolo | valore | motivo (codice) |
|---|---|---|
| `T_eur` | 0,01 € | importi arrotondati a 2 decimali in uscita (`round(x, 2)` in tutti i tool); soglia dell'audit originale (§E di `AUDIT_MCP_2026-11-02.md`: «0,01 €») |
| `T_sum_eur(n)` | 0,005 × n + 0,01 € | somma di n importi già arrotondati a 2 decimali: ogni addendo porta al più 0,005 |
| `T_pp` | 0,005 pp | una percentuale arrotondata a 2 decimali (`round(x, 2)`) confrontata con un valore esatto |
| `T_pp2` | 0,02 pp | confronto fra percentuali derivate da altre già arrotondate (fino a tre arrotondamenti a 2 decimali, 0,015, più margine float) |
| `T_sum_pp(n)` | 0,005 × n + 0,005 pp | somma di n percentuali arrotondate confrontata con un totale arrotondato |
| `T_w(n)` | max(0,05; 0,005 × n) pp | somma dei pesi: `Position.weight` arrotondato a 2 decimali per riga in `_positions.py` (`round(mv / totale × 100, 2)`); 0,05 è la soglia dell'audit originale, che però non regge oltre 10 posizioni |
| `T_ter` | 0,0005 pp | `ter_pct` e `weighted_ter_pct` di `get_cost_breakdown` arrotondati a 3 decimali |
| `T_ret` | 0,01 pp | TWR/MWR del servizio arrotondati a 4 decimali (`performance_service.py`); tolleranza predefinita di `scripts/audit/twr_mwr_offline_auditor.py` |
| `T_mc` | 3% relativo | mediana del Monte Carlo: 5.000 simulazioni con seed 42, errore campionario della mediana ≈ 1% a 10 anni con σ = 15%; 3% ≈ 3,5 deviazioni standard, ma l'esito è deterministico |
| `R_ter` | 0,01% ≤ TER ≤ 3,00% | gli ETF più economici sono allo 0,03% (VTI), i TER dedotti di `infer_ter` vanno da 0,07 a 0,25, i prodotti ordinari restano sotto il 2%; il difetto V-TER-UNIT dà valori 100 volte più piccoli (0,0075 per 0,75) e uno 100 volte più grande supera il 3% |
| `R_px` | 1/20 ≤ prezzo transazione / prezzo di mercato ≤ 20 | un cambio fra EUR, USD, GBP, CHF resta fra 0,5 e 2 e un prezzo può moltiplicarsi per 10 in un periodo di detenzione lungo; un prezzo per mille (V-XLSX-1000) o in pence letto come sterline (×100, V-QUOTE-CCY-L) esce dall'intervallo |
| `ε` | 1e-9 | margine float aggiunto a ogni confronto |

Le quantità di `get_positions` sono arrotondate a 8 decimali e `market_price` a 4: dove servono
compaiono nella scheda.

### 0.3 Comportamenti comuni

- **Portafoglio vuoto**: `scoped("get_positions")["positions"] == []` (o, per gli stress,
  `scenarios == []`) → `skip`/`empty_portfolio`.
- **Output troncato**: `get_positions` restituisce al più 30 righe. Scope `portfolio`:
  `len(positions) == 30` → troncato (prudenza: 30 righe possono essere tutte). Scope `aggregate`:
  `positions_count > len(positions)` → troncato. Le verifiche che richiedono tutte le righe vanno
  in `skip`/`truncated_output`; le altre restano.
- **Nomi degli scenari**: `get_stress_test` non espone l'id dello scenario. L'id si ricava da
  `scenario_name` con le tabelle `HISTORICAL_SCENARIOS` e `SHOCK_SCENARIOS` di
  `app/constants/stress_scenarios.py` (campo `name`). Un nome sconosciuto → `fail` (scenario non
  previsto dalla tabella approvata).
- **Tabelle di riferimento**: shock e proxy si leggono da `SHOCK_SCENARIOS` e
  `HISTORICAL_CLASS_PROXIES` (valori approvati il 2026-11-02, decisioni 7 e 12), non si copiano nel
  modulo della regola.
- **Export della performance**: prima di `ctx.performance_audit([pid])` la regola controlla
  `ctx.transactions(pid)`; lista vuota → `skip`/`no_transactions` (l'export di un portafoglio senza
  transazioni non è garantito e non serve). Per lo scope `aggregate` lo stesso vale se tutti i
  membri sono senza transazioni.
- **Funzione spenta**: se `read_doctor_metrics` restituisce l'errore di `POLICY_DISABLED_MESSAGE`
  (`app.copilot_doctor_tools`), le regole che lo leggono vanno in `skip`/`feature_disabled`
  (usano `try_call` solo per questo caso).

## 1. Portafogli di prova (contratto per TASK-78)

Utente `auditor-seed-user`, tutti i portafogli in EUR, id e asset con id ≥ 9101 (nessuna collisione
con `scripts/e2e/doctor2_seed.sql`). Date relative a `current_date`, prezzi e cambi nel seed, TER e
arricchimento nel seed, nessuna rete. Simboli fittizi (prefisso `AUD`), così la classificazione
dipende dai dati del seed e non dalle tabelle di simboli noti del classificatore. TASK-78 documenta
in `scripts/auditor/README.md` i valori risultanti (valore, pesi, liquidità) e li verifica nel test
di integrazione.

Strumenti (tabella `assets`; `etf_enrichment` = scheda justETF, `asset_metadata` = metadati yFinance):

| simbolo | tipo salvato | nome | dati di classificazione e costo | classe attesa |
|---|---|---|---|---|
| `AUDEQ.MI` | etf | AUD Global Equity UCITS ETF (Acc) | justETF: `investment_focus` «Equity, World», TER 0,22, `country_weights` (USA 62, Giappone 5,5, Regno Unito 3,5, Altri 29) | equity |
| `AUDBD.MI` | etf | AUD Global Aggregate Bond UCITS ETF EUR Hedged (Acc) | justETF: «Bonds, World, Aggregate», TER 0,10 | bond |
| `AUDTECH.DE` | etf | AUD Nasdaq-100 Technology UCITS ETF (Dist) | justETF: «Equity, United States, Technology», TER 0,30; `asset_metadata.dividend_yield` 0,6 | equity (tech: moltiplicatore 1,5 nel crollo tech) |
| `AUDGOV.MI` | etf | AUD Euro Government Bond UCITS ETF (Dist) | justETF: «Bonds, Euro, Government», TER 0,15; `dividend_yield` 2,5 | bond |
| `AUDHY.DE` | **stock** | AUD Euro High Yield Corporate Bond UCITS ETF (Dist) | nessuna scheda justETF; `asset_metadata.category` «High Yield Bond», `expense_ratio` 0,005 (frazione → 0,5%), `dividend_yield` 5,0 | bond (ETF obbligazionario tipizzato azione, caso V365-004) |
| `AUDBTP` | **bond** | BTP Italia 2030 1,6% | nessuna scheda; `dividend_yield` 1,6 | bond (titolo diretto, TER dedotto 0) |
| `AUDGLD.DE` | **stock** | AUD Physical Gold ETC | justETF: «Precious Metals, Gold», TER 0,25 | gold, `instrument_type` etc (caso V365-012) |
| `AUDCMD.MI` | etf | AUD Broad Commodity Swap UCITS ETF | justETF: «Commodities, Broad market», TER 0,19 | commodity |
| `AUDTHM.DE` | etf | AUD Thematic Frontier Opportunities UCITS ETF | nessuna scheda, nessun metadato | unknown (TER mancante) |
| `AUDUS.L` | etf | AUD World Equity UCITS ETF USD (Acc) | `quote_currency` USD; justETF «Equity, World», TER 0,20 | equity |
| `AUDUK.L` | etf | AUD UK Gilts UCITS ETF GBP (Dist) | `quote_currency` GBP; justETF «Bonds, United Kingdom, Government», TER 0,07; `dividend_yield` 3,0 | bond |
| `AUDSTL.MI` | etf | AUD Europe Equity UCITS ETF (Acc) | justETF «Equity, Europe», TER 0,12 | equity (quotazione ferma) |
| `AUDNPC.MI` | etf | AUD Emerging Markets Equity UCITS ETF (Acc) | justETF «Equity, Emerging Markets», TER 0,18 | equity (senza chiusura precedente) |

Portafogli:

| id | nome | composizione e requisiti | esercita |
|---|---|---|---|
| 9101 | AUD Bilanciato storico | `AUDEQ.MI` ≈ 70%, `AUDBD.MI` ≈ 20%, `AUDTECH.DE` ≈ 10% del valore investito; un deposito, gli acquisti e una vendita **negli ultimi 365 giorni** (deposito e acquisti nella stessa finestra: caso C1-TWR-MIXED); due dividendi EUR su `AUDTECH.DE`; liquidità residua > 0. **Target**: `AUDEQ.MI` 50, `AUDBD.MI` 40, `AUDTECH.DE` 10 (servono vendite per finanziare acquisti). **Prezzi**: per ogni strumento almeno due barre dentro ciascuna finestra storica (2007-10-01…2009-03-31, 2000-03-01…2002-10-31, 2020-02-19…2020-03-23, 2022-01-03…2022-10-12) → metodo `historical`; barre giornaliere per gli ultimi 400 giorni di calendario (≥ 20 rendimenti nell'ultimo anno), barra di oggi e di ieri con prezzi diversi | quasi tutto: A stress storico, B, C costi/reddito/Monte Carlo/movers, D performance, X-Ray, Doctor |
| 9102 | AUD Solo obbligazioni | `AUDGOV.MI`, `AUDHY.DE`, `AUDBTP`; nessuna barra nelle finestre storiche (solo ultimi 30 giorni) → metodo `proxy`; nessun target | stress con proxy, reddito obbligazionario, TER da yFinance normalizzato, tipo `bond` |
| 9103 | AUD Oro e materie prime | `AUDGLD.DE` ≈ 40%, `AUDCMD.MI` ≈ 20%, `AUDTHM.DE` ≈ 15%, `AUDEQ.MI` ≈ 25%; solo barre recenti | classificazione ETC, shock oro/commodity, classe unknown, copertura TER parziale, metrica oro del Doctor |
| 9104 | AUD Londra e valute | `AUDUS.L` (acquisti in USD), `AUDUK.L` (acquisti in GBP), `AUDEQ.MI` (EUR); cambi EUR/USD ed EUR/GBP giornalieri per tutto il periodo delle transazioni e dei prezzi; dividendi in GBP su `AUDUK.L` e in EUR su `AUDEQ.MI` | valuta di quotazione dei listing di Londra, scala dei prezzi con cambio, dividendi in più valute |
| 9105 | AUD Import | transazioni di un lotto d'import confermato (`csv_import_batches`) su `AUDEQ.MI` e `AUDBD.MI`; **una coppia legittima** di acquisti identici nello stesso giorno (esecuzione frazionata); dividendi EUR mensili su date diverse; nessun duplicato reale | duplicati (nessun falso positivo), dividendi in una valuta |
| 9106 | AUD Vuoto | nessuna transazione, `cash_balance` 0 | `skip`/`empty_portfolio` |
| 9107 | AUD Quotazioni ferme | `AUDSTL.MI` con ultima barra di 30 giorni fa (prezzo fermo); `AUDNPC.MI` con una sola barra (oggi) e nessun tick (nessuna chiusura precedente); `AUDEQ.MI` con barre di oggi e di ieri diverse | variazioni giornaliere, flag di qualità dei dati |

Scope che ne derivano: 7 scope `portfolio`; 1 scope `aggregate` [9101…9107]; uno scope
`instrument` per ogni posizione; 1 scope `user`. Nessuna policy del Doctor precaricata (le regole
lette qui non ne hanno bisogno). Il seed non chiama l'import CSV: «tentativo di import duplicato» è
rappresentato dal lotto confermato più la coppia legittima, mentre il duplicato vero si riproduce
nei test unitari (TASK-77).

## 2. Gruppo A — stress test e classificazione (TASK-74, `rules/stress_classification.py`)

### A-STRESS-HIST-DISTINCT
- **Titolo:** Gli scenari storici danno risultati diversi per portafogli con composizione diversa
- **Sev.** P0 · **Area** stress · **Finding** V365-001 · **Scope** user · timeout 60 s
- **Tool:** `get_stress_test` `{"portfolio_id": p}` per ogni p di `scope.portfolio_ids`.
- **Condizione:** idonei = portafogli con almeno uno scenario `scenario_type == "historical"` e
  `method != "not_available"`. Per ciascuno, vettore di classe = `weight_pct` per `asset_class` di
  `class_breakdown` dello scenario a shock «Global Equity Crash». Per ogni coppia di idonei con
  distanza L1 fra i vettori > 1,0 pp: **non** deve valere `|impatto_p − impatto_q| ≤ 0,01` per tutti
  e quattro gli scenari storici (`estimated_portfolio_impact_pct`, appaiati per `scenario_name`).
- **Tolleranze:** uguaglianza a 0,01 pp (impatti a 2 decimali); soglia di composizione 1,0 pp (due
  portafogli con la stessa miscela di classi possono legittimamente coincidere col metodo proxy).
- **Skip:** meno di 2 portafogli idonei → `not_applicable`.
- **Prova:** scope user del seed (9101 storico, 9102 e 9103 proxy).
- **Difetto:** gli stessi quattro impatti per tutti i portafogli (−45,44 / −39,28 / −27,12 / −20,32,
  il vecchio `benchmark_drawdown × 0,8`).

### A-STRESS-PROXY-TABLE
- **Titolo:** Le stime storiche senza prezzi usano i valori approvati per ogni classe di attivo
- **Sev.** P0 · **Area** stress · **Finding** V365-001 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_stress_test")`.
- **Condizione:** per ogni scenario storico con `method` in (`historical`, `proxy`):
  `class_breakdown` non vuoto; per ogni riga con `source == "proxy"`: `drawdown_pct` =
  `HISTORICAL_CLASS_PROXIES[id][asset_class]`, dove un valore `None` (cripto prima del 2010) o una
  classe assente dalla tabella (`unknown`) valgono il proxy `equity`; con `method == "proxy"` tutte
  le righe hanno `source == "proxy"`.
- **Tolleranze:** `T_pp` (i proxy sono interi; `drawdown_pct` = contributo / peso × 100 arrotondato).
- **Skip:** `scenarios == []` → `empty_portfolio`; tutti gli storici `not_available` →
  `scenario_not_available`.
- **Prova:** 9102, 9103 (proxy), aggregato (parte scoperta di 9102/9103).
- **Difetto:** scenario storico senza `class_breakdown`, oppure `drawdown_pct` uguale per tutte le
  classi (stesso numero del benchmark).

### A-STRESS-METHOD-COVERAGE
- **Titolo:** Ogni scenario storico dichiara metodo e copertura dei prezzi reali
- **Sev.** P1 · **Area** stress · **Finding** V365-001 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_stress_test")`.
- **Condizione:** per ogni scenario storico: `method` ∈ {`historical`, `proxy`, `not_available`};
  `historical` ⇔ `coverage_pct` ≥ 60 (`HISTORICAL_MIN_COVERAGE_PCT`); `proxy` ⇔ `coverage_pct` < 60;
  `not_available` ⇔ `coverage_pct` è null; `proxy` ⇒ `"class_proxy_drawdowns"` ∈ `flags`; almeno una
  riga con `source == "proxy"` ⇒ `methodology_note` presente e non vuota (limite USD, decisione 12).
- **Tolleranze:** nessuna (`coverage_pct` è già arrotondato prima del confronto nel codice).
- **Skip:** `scenarios == []` → `empty_portfolio`.
- **Prova:** 9101 (historical), 9102 (proxy), aggregato.
- **Difetto:** scenario storico senza `method` o con `method: "proxy"` e `coverage_pct` 80.

### A-STRESS-CONTRIB-SUM
- **Titolo:** Nello stress test i contributi delle classi sommano all'impatto totale
- **Sev.** P1 · **Area** stress · **Finding** V365-001, V365-002 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_stress_test")`.
- **Condizione:** per ogni scenario con `class_breakdown` non vuoto (storici non `not_available` e a
  shock): `|Σ contribution_pct − estimated_portfolio_impact_pct| ≤ T_sum_pp(k)` con k righe; per gli
  scenari a shock, per ogni riga con `asset_class` ∉ {`equity`, `unknown`}:
  `|weight_pct × shock_pct / 100 − contribution_pct| ≤ T_pp2` (le classi non azionarie non hanno
  moltiplicatore).
- **Tolleranze:** `T_sum_pp(k)`, `T_pp2`.
- **Skip:** `scenarios == []` → `empty_portfolio`.
- **Prova:** 9101, 9102, 9103, aggregato.
- **Difetto:** contributo di una classe alterato (o impatto calcolato su un peso diverso).

### A-STRESS-SHOCK-TABLE
- **Titolo:** Lo stress test applica a ogni classe di attivo lo shock previsto
- **Sev.** P0 · **Area** stress · **Finding** V365-002 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_stress_test")`.
- **Condizione:** per ogni scenario a shock e ogni riga di `class_breakdown`: se `asset_class` è una
  chiave di `shocks` dello scenario, `shock_pct` = `shocks[asset_class] × 100`; se è `unknown`,
  `shock_pct` = `shocks["equity"] × 100` **e** `"unknown_asset_class_equity_shock"` ∈ `flags`;
  nessun'altra classe ammessa.
- **Tolleranze:** `T_pp`.
- **Skip:** `scenarios == []` → `empty_portfolio`.
- **Prova:** 9102 (bond), 9103 (gold, commodity, unknown), 9101.
- **Difetto:** riga `bond` (o `gold`) con lo shock equity (−20 nel Global Equity Crash, −30 nel crollo
  tech).

### A-STRESS-NONEQUITY-POSITION-SHOCK
- **Titolo:** Obbligazioni, oro e materie prime non ricevono lo shock delle azioni
- **Sev.** P0 · **Area** stress · **Finding** V365-002 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_stress_test")`.
- **Condizione:** per ogni scenario, ogni voce di `most_impacted` ha `loss_pct` < 0 (solo perdite
  reali). Negli scenari a shock: voce con `asset_class` ∉ {`equity`, `unknown`} →
  `loss_pct` = `shocks[asset_class] × 100`; voce `equity` → `loss_pct` ∈ {`s`, `1,5 × s`} con
  `s = shocks["equity"] × 100` (il secondo valore solo nello scenario con `tech_multiplier`).
- **Tolleranze:** `T_pp`.
- **Skip:** `scenarios == []` → `empty_portfolio`; nessuna voce `most_impacted` in nessuno scenario →
  `not_applicable`.
- **Prova:** 9101 (tech), 9103.
- **Difetto:** `most_impacted` con un ETF obbligazionario a −30% nel crollo tech, o con una voce a
  perdita 0.

### A-CLASS-STRESS-CONSISTENT
- **Titolo:** Lo stress test classifica gli strumenti come la scheda dello strumento
- **Sev.** P0 · **Area** classification · **Finding** V365-002, V365-012 · **Scope** portfolio
- **Tool:** `get_positions`; `search_asset_info` `{"symbol": s}` per ogni riga; `get_stress_test`.
- **Condizione:** pesi per classe secondo la scheda = Σ `weight` delle righe di `get_positions`
  raggruppate per `asset_class` di `search_asset_info`; pesi secondo lo stress = `weight_pct` per
  `asset_class` nel `class_breakdown` di «Global Equity Crash». Le due mappe hanno le stesse classi
  e per ogni classe `|differenza| ≤ T_sum_pp(n_classe)`.
- **Tolleranze:** `T_sum_pp(n)` (stessi pesi a 2 decimali sommati in due punti).
- **Skip:** `empty_portfolio`; righe troncate → `truncated_output`.
- **Prova:** 9101, 9102, 9103.
- **Difetto:** il vecchio `_shock_asset_class` (classe `equity` per tutto ciò che non è `bond`):
  lo stress mostra `equity` dove la scheda dice `bond`/`gold`.

### A-CLASS-ETC-NOT-EQUITY
- **Titolo:** Gli ETC su oro e metalli preziosi non sono classificati come azioni
- **Sev.** P1 · **Area** classification · **Finding** V365-012 · **Scope** instrument
- **Tool:** `search_asset_info` `{"symbol": scope.symbol}`.
- **Condizione:** se `instrument_type == "etc"`: `asset_class` ∈ {`gold`, `commodity`}. Inoltre, se
  `instrument_type` ∈ {`etc`, `etn`} e il `name` contiene (senza distinzione di maiuscole, parola
  intera) gold, oro, silver, argento, platinum, platino, palladium, palladio, precious: `asset_class`
  ≠ `equity`.
- **Tolleranze:** nessuna.
- **Skip:** `instrument_type` ∉ {`etc`, `etn`} → `not_applicable`.
- **Prova:** `AUDGLD.DE` in 9103.
- **Difetto:** `QUOTE_TYPE_MAP` vecchio (EQUITY → stock) senza la regola ETC del classificatore:
  `asset_class: "equity"` per un ETC sull'oro. Severità P1 (il finding era P2) perché la classe
  alimenta lo stress test (P0) e il peso azionario del Doctor.

### A-CLASS-ETP-TER-NONZERO
- **Titolo:** ETF ed ETC non risultano a costo zero per un TER dedotto
- **Sev.** P2 · **Area** classification · **Finding** V365-012, V365-007 · **Scope** instrument
- **Tool:** `search_asset_info`; `get_cost_breakdown` `{"portfolio_id": scope.portfolio_id}`.
- **Condizione:** se `instrument_type` ∈ {`etc`, `etn`, `etf`, `fund`} e la riga di `position_costs`
  con lo stesso `symbol` esiste: non vale (`ter_source == "inferred"` e `ter_pct == 0`).
- **Tolleranze:** nessuna (0 esatto).
- **Skip:** `instrument_type` fuori da quell'insieme → `not_applicable`; riga assente (le righe sono
  al più 20) → `truncated_output`.
- **Prova:** strumenti ETF/ETC di 9101, 9103.
- **Difetto:** `infer_ter` che restituisce 0 per un ETC tipizzato `stock`.

### A-CLASS-BOND-TYPE
- **Titolo:** Un fondo obbligazionario non è registrato come singola obbligazione
- **Sev.** P2 · **Area** classification · **Finding** V-BOND-QUOTETYPE · **Scope** instrument
- **Tool:** `search_asset_info`.
- **Condizione:** se `type == "bond"`: il `name` non contiene (parola intera, senza distinzione di
  maiuscole) ETF, UCITS, ETC, ETN, FUND, FONDO, SICAV.
- **Tolleranze:** nessuna.
- **Skip:** `type != "bond"` → `not_applicable`.
- **Prova:** `AUDBTP` in 9102.
- **Difetto:** `resolve_refreshed_asset_type` che trasforma un etf con quote type BOND in `bond`
  (scheda con `type: "bond"` e nome «… UCITS ETF»). Limite: il refresh non gira durante l'audit
  (provider offline), quindi la regola vede solo lo stato salvato.

### A-CLASS-UNKNOWN-DECLARED
- **Titolo:** Gli strumenti non classificabili sono dichiarati, non trattati in silenzio come azioni
- **Sev.** P2 · **Area** classification · **Finding** V365-002 (decisione 3) · **Scope** instrument
- **Tool:** `search_asset_info`; `get_stress_test` `{"portfolio_id": scope.portfolio_id}`.
- **Condizione:** se `asset_class == "unknown"`: ogni scenario a shock ha
  `"unknown_asset_class_equity_shock"` ∈ `flags` e una riga `class_breakdown` con
  `asset_class == "unknown"`.
- **Tolleranze:** nessuna.
- **Skip:** `asset_class != "unknown"` → `not_applicable`.
- **Prova:** `AUDTHM.DE` in 9103.
- **Difetto:** strumento `unknown` sommato alla riga `equity` senza flag.

## 3. Gruppo B — ribilanciamento, PAC e simulazioni (TASK-75, `rules/rebalance_simulation.py`)

Argomenti fissi (architettura §5.2): ribilanciamento in tre modalità — R = `{"mode": "rebalance"}`,
BO = `{"mode": "buy_only", "available_cash": 1000.0}`, SO = `{"mode": "sell_only"}`; PAC
`{"monthly_amount": 500.0}`; what-if su S = simbolo della prima riga di `get_positions`.
`calculate_rebalance_orders` senza target restituisce `{"mode", "orders": [], "note"}` senza
`totals`: **assenza di `totals` → `skip`/`no_targets`**. `calculate_pac_contribution` senza target
restituisce `{"distribution": [], "note"}` senza `total_allocated` → `skip`/`no_targets`.
n = numero di ordini (o di righe della distribuzione).

### B-REB-CASH-CONSERVATION
- **Titolo:** Il ribilanciamento conserva la liquidità: vendite e acquisti tornano al centesimo
- **Sev.** P0 · **Area** rebalance · **Finding** V365-003 · **Scope** portfolio
- **Tool:** `calculate_rebalance_orders` con R, BO, SO.
- **Condizione:** per ogni modalità: `|totals.cash_after − (totals.cash_before + totals.extra_cash +
  totals.sells_eur − totals.buys_eur)| ≤ T_eur`; `|totals.sells_eur − Σ amount_eur degli ordini
  "sell"| ≤ T_sum_eur(n)`; idem per `buys_eur`; `totals.invariant_ok is True`; BO:
  `totals.extra_cash == 1000.0`.
- **Tolleranze:** `T_eur`, `T_sum_eur(n)`.
- **Skip:** `empty_portfolio`; `no_targets`.
- **Prova:** 9101.
- **Difetto:** output di novembre: sola vendita di 815,07 € con `cash_after` 0 (i proventi spariscono).

### B-REB-CASH-NONNEG
- **Titolo:** Il ribilanciamento non spende più della liquidità disponibile
- **Sev.** P0 · **Area** rebalance · **Finding** V365-003 · **Scope** portfolio
- **Tool:** `calculate_rebalance_orders` con R, BO, SO.
- **Condizione:** per ogni modalità: `totals.cash_after ≥ −T_eur` e `totals.buys_eur ≤
  totals.cash_before + totals.extra_cash + totals.sells_eur + T_sum_eur(n)`.
- **Tolleranze:** `T_eur`, `T_sum_eur(n)`.
- **Skip:** `empty_portfolio`; `no_targets`.
- **Prova:** 9101.
- **Difetto:** liquidità contata due volte (`cash_used` = liquidità + liquidità): acquisti oltre il
  disponibile, `cash_after` negativo.

### B-REB-SELLS-REACH-TARGET
- **Titolo:** Le vendite del ribilanciamento portano ogni strumento al suo peso obiettivo
- **Sev.** P1 · **Area** rebalance · **Finding** V365-003 · **Scope** portfolio
- **Tool:** `calculate_rebalance_orders` con R e SO.
- **Condizione:** ogni ordine `sell`: `|weight_after_pct − target_weight_pct| ≤ T_pp2`. Con R, ogni
  ordine `buy`: `weight_after_pct ≤ target_weight_pct + T_pp2`; se almeno un `buy` ha
  `weight_after_pct < target_weight_pct − T_pp2` (acquisti ridotti), allora `totals.cash_after ≤
  T_sum_eur(n)`: in `compute_rebalance_plan` gli acquisti si riducono solo quando liquidità e
  proventi non bastano, e allora `cash_after` è 0 prima degli arrotondamenti.
- **Tolleranze:** `T_pp2`, `T_sum_eur(n)`.
- **Skip:** `empty_portfolio`; `no_targets`; nessun ordine in R e SO → `not_applicable`.
- **Prova:** 9101.
- **Difetto:** vendita = scostamento % × valore della posizione (non porta al target) senza acquisti.

### B-REB-DRIFT-NONINCREASING
- **Titolo:** Dopo gli ordini lo scostamento dai pesi obiettivo non aumenta
- **Sev.** P1 · **Area** rebalance · **Finding** V365-003 · **Scope** portfolio
- **Tool:** `calculate_rebalance_orders` con R, BO, SO.
- **Condizione:** per ogni ordine di ogni modalità: `|weight_after_pct − target_weight_pct| ≤
  |current_weight_pct − target_weight_pct| + T_pp2`.
- **Tolleranze:** `T_pp2`.
- **Skip:** `empty_portfolio`; `no_targets`; nessun ordine in nessuna modalità → `not_applicable`.
- **Prova:** 9101.
- **Difetto:** acquisto su uno strumento già sovrappesato (segno dell'ordine invertito).

### B-REB-MODE-SIDES
- **Titolo:** Con sola nuova liquidità il ribilanciamento non propone vendite
- **Sev.** P1 · **Area** rebalance · **Finding** V365-003 (decisione 1) · **Scope** portfolio
- **Tool:** `calculate_rebalance_orders` con BO e SO.
- **Condizione:** BO: nessun ordine con `side == "sell"` e `totals.sells_eur == 0`; SO: nessun
  ordine `buy` e `totals.buys_eur == 0`.
- **Tolleranze:** nessuna.
- **Skip:** `empty_portfolio`; `no_targets`.
- **Prova:** 9101.
- **Difetto:** modalità ignorata (BO che restituisce le vendite di R).

### B-REB-SELL-CAP
- **Titolo:** Non si vende mai più di quanto si possiede
- **Sev.** P1 · **Area** rebalance · **Finding** V365-003 · **Scope** portfolio
- **Tool:** `calculate_rebalance_orders` con R e SO; `get_positions`.
- **Condizione:** per ogni ordine `sell`: esiste la riga di `get_positions` con lo stesso `symbol` e
  `amount_eur ≤ market_value + T_eur`.
- **Tolleranze:** `T_eur`.
- **Skip:** `empty_portfolio`; `no_targets`; nessuna vendita → `not_applicable`; simbolo di una
  vendita assente dalle righe e righe troncate → `truncated_output`.
- **Prova:** 9101.
- **Difetto:** vendita calcolata sul totale del portafoglio invece che sulla posizione.

### B-PAC-SUM
- **Titolo:** Nel PAC la somma dei versamenti per strumento è uguale all'importo indicato
- **Sev.** P1 · **Area** rebalance · **Finding** — (proprietà di conservazione; audit §E) · **Scope** portfolio
- **Tool:** `calculate_pac_contribution` `{"monthly_amount": 500.0}`.
- **Condizione:** `monthly_amount == 500.0`; `|total_allocated − 500.0| ≤ T_eur`;
  `|Σ distribution[].amount_eur − total_allocated| ≤ T_sum_eur(n)`.
- **Tolleranze:** `T_eur`, `T_sum_eur(n)`.
- **Skip:** `empty_portfolio`; `no_targets`.
- **Prova:** 9101.
- **Difetto:** distribuzione vuota con `total_allocated` 500 (tutti gli strumenti già a target o
  sopra: il ramo «remaining» del codice attuale distribuisce il residuo solo sulle righe già presenti
  e azzera `remaining` anche se non ce ne sono). Nota: è un **difetto probabile del codice attuale**
  quando i target sommano meno di 100 o nessuno strumento è sottopesato; TASK-79 verifica e, se si
  conferma, apre il task e marca `known_defect`.

### B-PAC-UNDERWEIGHT-ONLY
- **Titolo:** Il PAC versa solo sugli strumenti sotto il peso obiettivo
- **Sev.** P2 · **Area** rebalance · **Finding** — · **Scope** portfolio
- **Tool:** `calculate_pac_contribution` `{"monthly_amount": 500.0}`; `get_target_drift`.
- **Condizione:** ogni riga di `distribution` ha `amount_eur ≥ 0`, `current_weight ≤ target_weight +
  T_pp2` e `symbol` presente fra i `symbol` di `get_target_drift.drift`.
- **Tolleranze:** `T_pp2`.
- **Skip:** `empty_portfolio`; `no_targets`; distribuzione vuota → `not_applicable`.
- **Prova:** 9101.
- **Difetto:** versamento su uno strumento sovrappesato.

### B-WHATIF-BUY-WEIGHT
- **Titolo:** La simulazione di un acquisto ricalcola correttamente il peso
- **Sev.** P2 · **Area** simulation · **Finding** — · **Scope** portfolio
- **Tool:** `get_positions`, `get_portfolio_summary`, `calculate_what_if`
  `{"action": "buy", "symbol": S, "amount_eur": 1000.0}`.
- **Condizione:** con MV = `get_portfolio_summary.market_value` e w = `weight` della riga S:
  `|old_weight − w| ≤ T_pp`; `|new_weight − (w × MV / 100 + 1000) / (MV + 1000) × 100| ≤ T_pp2`;
  `max_position_weight_after ≥ new_weight − T_pp`.
- **Tolleranze:** `T_pp`, `T_pp2`.
- **Skip:** `empty_portfolio`.
- **Prova:** 9101.
- **Difetto:** nuovo peso calcolato sul totale prima dell'acquisto.

### B-WHATIF-SELL-BOUND
- **Titolo:** La simulazione di una vendita ricalcola il peso e rifiuta vendite oltre la posizione
- **Sev.** P2 · **Area** simulation · **Finding** — · **Scope** portfolio
- **Tool:** `get_positions`, `get_portfolio_summary`, `calculate_what_if` con
  `{"action": "sell", "symbol": S, "amount_eur": A}` (A = `round(V / 2, 2)`, V = `market_value`
  della riga S) e con `amount_eur` = `round(V + 1000.0, 2)` via `try_call`.
- **Condizione:** prima chiamata: `|new_weight − (w × MV / 100 − A) / (MV − A) × 100| ≤ T_pp2`;
  seconda chiamata: `ok is False` (il tool rifiuta la vendita oltre il valore della posizione).
- **Tolleranze:** `T_pp2`.
- **Skip:** `empty_portfolio`; V < 0,02 € → `not_applicable`.
- **Prova:** 9101.
- **Difetto:** vendita oltre la posizione accettata con peso negativo.

## 4. Gruppo C — costi, reddito, dividendi, Monte Carlo, variazioni (TASK-76, `rules/costs_income.py`)

### C-TER-RANGE
- **Titolo:** I costi annui dei fondi (TER) sono in un intervallo plausibile
- **Sev.** P1 · **Area** costs · **Finding** V-TER-UNIT, V365-007 · **Scope** portfolio
- **Tool:** `get_cost_breakdown`.
- **Condizione:** ogni riga di `position_costs` con `ter_source` ∈ {`justetf`, `yfinance`}, e ogni
  riga `inferred` con `ter_pct > 0`, ha `ter_pct` in `R_ter`; `weighted_ter_pct`, se non null, è in
  [0; 3,00].
- **Tolleranze:** `R_ter` (estremi inclusi, già comprensivi dell'arrotondamento a 3 decimali).
- **Skip:** `empty_portfolio`; nessuna riga con TER → `no_reference_data`.
- **Prova:** 9101 (justETF), 9102 (yFinance 0,005 → 0,5), 9103.
- **Difetto:** `meta.expense_ratio` letto senza `normalize_expense_ratio_pct` (0,0075 → «0,0075%»
  invece di 0,75%).

### C-COST-COHERENCE
- **Titolo:** Il costo annuo stimato è coerente con il TER medio e il valore coperto
- **Sev.** P1 · **Area** costs · **Finding** V365-007 · **Scope** portfolio
- **Tool:** `get_cost_breakdown`.
- **Condizione:** se `weighted_ter_pct` non è null, con C = `covered_market_value_eur` e w =
  `weighted_ter_pct`: `|estimated_annual_cost_known_eur − C × w / 100| ≤ T_eur + C × 5e-6`;
  `|fee_drag_10y_eur − C × (1 − (1 − w / 100)^10)| ≤ T_eur + C × 5e-5`;
  `total_annual_cost_eur == estimated_annual_cost_known_eur`; `C ≤ portfolio_market_value + T_eur`;
  `Σ annual_cost_eur` delle righe ≤ `estimated_annual_cost_known_eur + T_sum_eur(righe)`
  (le righe sono al più 20); `cost_perimeter == "covered_positions"`. Se `weighted_ter_pct` è null:
  `estimated_annual_cost_known_eur` e `fee_drag_10y_eur` sono null.
- **Tolleranze:** `T_eur` più l'effetto di `T_ter` sul valore coperto (C × 0,0005 / 100 sul costo,
  dieci volte tanto sul fee drag), `T_sum_eur`.
- **Skip:** `empty_portfolio`.
- **Prova:** 9101, 9103 (copertura parziale).
- **Difetto:** costo annuo calcolato sul valore totale con il TER medio del solo perimetro coperto
  (All Weather di novembre: TER 0,03% su copertura 34,86% presentato come completo).

### C-COST-COVERAGE-DECLARED
- **Titolo:** Quando mancano dei TER, la copertura incompleta è dichiarata
- **Sev.** P1 · **Area** costs · **Finding** V365-007 · **Scope** portfolio
- **Tool:** `get_cost_breakdown`.
- **Condizione:** `missing_ter_symbols` non vuoto ⇔ `ter_coverage_pct < 100`; `ter_coverage_pct < 100`
  ⇒ `coverage_note` non vuota e contiene ogni simbolo mancante; ogni riga di `position_costs` con
  `ter_pct` null ha il `symbol` in `missing_ter_symbols`; ogni riga con `ter_source == "inferred"` ha
  il `symbol` in `inferred_ter_symbols`.
- **Tolleranze:** nessuna (`ter_coverage_pct` a 1 decimale, confronto con 100 esatto come nel codice).
- **Skip:** `empty_portfolio`.
- **Prova:** 9103 (`AUDTHM.DE` senza TER), 9101 (copertura piena).
- **Difetto:** TER mancante escluso in silenzio (`missing_ter_symbols` vuoto con copertura < 100).

### C-INCOME-BUCKETS-SUM
- **Titolo:** Il reddito stimato per classe somma al reddito totale
- **Sev.** P1 · **Area** income · **Finding** V365-004 · **Scope** portfolio
- **Tool:** `get_income_projection`.
- **Condizione:** `|equity_annual_dividends_eur + fixed_income_annual_dividends_eur +
  other_or_unknown_annual_dividends_eur − current_annual_dividends_gross_eur| ≤ 0,02 €`; `|current_annual_dividends_net_eur − gross × (1 − tax_rate_pct / 100)| ≤ T_eur`;
  `[p.years for p in projections] == [1, 3, 5]`; per ogni proiezione `cumulative_net_eur ≤
  cumulative_gross_eur + T_eur`.
- **Tolleranze:** 0,02 € (quattro importi arrotondati a 2 decimali), `T_eur`.
- **Skip:** `empty_portfolio`.
- **Prova:** 9101, 9102.
- **Difetto:** reddito obbligazionario escluso dai bucket (somma dei bucket < lordo).

### C-INCOME-CLASS-RECOMPUTE
- **Titolo:** Il reddito degli ETF obbligazionari è conteggiato come reddito fisso, non azionario
- **Sev.** P1 · **Area** income · **Finding** V365-004, V-INCOME-TYPE · **Scope** portfolio
- **Tool:** `get_positions`; `search_asset_info` per ogni riga; `get_income_projection`.
- **Condizione:** per ogni riga con `dividend_yield` di `search_asset_info` > 0: contributo =
  `market_value × dividend_yield / 100`, nel bucket `equity` se `asset_class == "equity"`,
  `fixed_income` se `bond`, altrimenti `other_or_unknown`. Per ogni bucket
  `|ricalcolo − <bucket>_annual_dividends_eur| ≤ T_eur + 1e-6 × ricalcolo` (nomi dei campi:
  `equity_annual_dividends_eur`, `fixed_income_annual_dividends_eur`,
  `other_or_unknown_annual_dividends_eur`).
- **Tolleranze:** `T_eur` (stessi `market_value` e rendimenti; un solo arrotondamento in uscita).
- **Skip:** `empty_portfolio`; `truncated_output`; nessuna riga con rendimento → `no_reference_data`.
- **Prova:** 9102 (`AUDHY.DE` tipizzato stock, `AUDGOV.MI`, `AUDBTP`), 9101 (`AUDTECH.DE`).
- **Difetto:** `asset_type` letto da `get_asset_by_symbol` (che non lo restituisce): tutto il reddito
  in `equity`, `fixed_income_annual_dividends_eur` = 0.

### C-MC-YEARS
- **Titolo:** La proiezione Monte Carlo copre esattamente gli anni da 1 a 10, come indice base 100
- **Sev.** P1 · **Area** montecarlo · **Finding** V365-006 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_monte_carlo")`, `scoped("get_positions")` (solo per riconoscere il
  portafoglio vuoto).
- **Condizione:** `[p["year"] for p in projections] == [1, 2, …, 10]`; `unit == "indice_base_100"`;
  `initial_value == 100`.
- **Tolleranze:** nessuna.
- **Skip:** `empty_portfolio` (da `get_positions`); `projections == []` con posizioni → `no_history`.
- **Prova:** 9101, 9103, aggregato.
- **Difetto:** `projections[:10]` prima del filtro `year > 0` (anni 0…9 o 1…9).

### C-MC-PERCENTILES
- **Titolo:** I percentili della proiezione Monte Carlo sono ordinati
- **Sev.** P1 · **Area** montecarlo · **Finding** V365-006 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_monte_carlo")`.
- **Condizione:** per ogni anno `0 < p25 ≤ p50 ≤ p75`. Il tool espone P25/P50/P75 (non P10/P90:
  vedi §9).
- **Tolleranze:** nessuna (l'arrotondamento a 1 decimale è monotono e non rompe l'ordine).
- **Skip:** come C-MC-YEARS.
- **Prova:** 9101, 9103, aggregato.
- **Difetto:** percentili scambiati (`p25` > `p50`).

### C-MC-MEDIAN-DRIFT
- **Titolo:** La mediana della proiezione segue il rendimento atteso dichiarato
- **Sev.** P2 · **Area** montecarlo · **Finding** V365-006 (unità non dichiarata) · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_monte_carlo")`.
- **Condizione:** per ogni anno y: `|p50 / (100 × (1 + annualized_mean_return_pct / 100)^y) − 1| ≤
  T_mc` (con drift ln(1 + μ) e shock simmetrici la mediana del percorso è 100 × (1 + μ)^y).
- **Tolleranze:** `T_mc`.
- **Skip:** come C-MC-YEARS.
- **Prova:** 9101, aggregato.
- **Difetto:** percentili in euro invece che in indice (p50 dell'anno 1 pari al valore del
  portafoglio).

### C-DIV-CURRENCY
- **Titolo:** I dividendi incassati sono totalizzati per valuta, senza sommare valute diverse
- **Sev.** P2 · **Area** income · **Finding** V-DIV-MIXED-CCY, V365-009 · **Scope** portfolio
- **Tool:** `get_dividend_summary`; `ctx.transactions(portfolio_id)`.
- **Condizione:** ricalcolo dalle transazioni con `side == "dividend"`, per
  `trade_currency.upper()` (vuota → «N/D»): totale = Σ `quantity × price`, conteggio. Le chiavi di
  `dividends_by_currency` sono esattamente le valute del ricalcolo; per ciascuna
  `|total − ricalcolo| ≤ T_eur` e `count` uguale; `dividend_transactions_count` = numero totale;
  `mixed_currencies` ⇔ più di una valuta; se `mixed_currencies`: `total_dividends_received`,
  `dividends_last_12m` e `dividends_currency` sono null e `currency_note` è presente; altrimenti
  `|total_dividends_received − total della sola valuta| ≤ T_eur` e `dividends_currency` è quella
  valuta.
- **Tolleranze:** `T_eur`.
- **Skip:** nessuna transazione `dividend` → `no_reference_data`.
- **Prova:** 9104 (GBP + EUR), 9105 (EUR), 9101 (EUR).
- **Difetto:** totale unico che somma GBP ed EUR.

### C-DAYMOVERS-NONZERO-INCLUDED
- **Titolo:** Le variazioni giornaliere disponibili compaiono fra migliori e peggiori
- **Sev.** P1 · **Area** daily · **Finding** V365-005, V-DAYMOVERS-ROOT · **Scope** portfolio
- **Tool:** `get_positions`; `get_day_movers`.
- **Condizione:** sia F l'insieme delle righe di `get_positions` con `price_stale` falso,
  `price_date` non null e `day_change_pct != 0` (una variazione non nulla esiste solo con una
  chiusura precedente, `_positions.py`). Se F non è vuoto: `valid_positions ≥ 1`, `best` e `worst` non
  null e per ogni riga di F `worst.day_change_pct − T_pp ≤ day_change_pct ≤ best.day_change_pct +
  T_pp`.
- **Tolleranze:** `T_pp`.
- **Skip:** `empty_portfolio`; F vuoto → `no_reference_data` (mercato chiuso, giornata piatta o
  nessuna chiusura precedente).
- **Prova:** 9101, 9107.
- **Difetto:** fonte sbagliata (rendimenti a 1 anno dei target): `best`/`worst` null con variazioni
  disponibili.

### C-DAYMOVERS-CONSISTENCY
- **Titolo:** Migliori e peggiori del giorno escludono le quotazioni ferme e senza chiusura precedente
- **Sev.** P1 · **Area** daily · **Finding** V-DAYMOVERS-ROOT, V365-005 · **Scope** portfolio
- **Tool:** `get_positions`; `get_day_movers`.
- **Condizione:** `best is None` ⇔ `worst is None` ⇔ `valid_positions == 0`; con `best` null
  `reason` è una stringa non vuota; con `valid_positions ≥ 1`: `best.day_change_pct ≥
  worst.day_change_pct`, i simboli di `best` e `worst` non compaiono in `stale_positions[].symbol` e
  le loro righe in `get_positions` (se presenti) hanno `price_stale` falso; `valid_positions == 1` ⇒
  `best.symbol == worst.symbol`; se le righe non sono troncate: `valid_positions + excluded_stale +
  excluded_no_previous_close == len(positions)`.
- **Tolleranze:** nessuna.
- **Skip:** `empty_portfolio`.
- **Prova:** 9107 (fermo + senza chiusura precedente + valido), 9101.
- **Difetto:** `day_change_pct = 0.0` di default trattato come variazione (posizione senza chiusura
  precedente indicata come «peggiore» a 0%).

## 5. Gruppo D — coerenza fra tool, vista aggregata e dati (TASK-77, `rules/consistency.py`)

### D-WEIGHTS-SUM
- **Titolo:** I pesi delle posizioni sommano a cento
- **Sev.** P1 · **Area** values · **Finding** — (audit §E) · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_positions")`.
- **Condizione:** `|Σ weight − 100| ≤ T_w(n)`.
- **Tolleranze:** `T_w(n)`.
- **Skip:** `empty_portfolio`; `truncated_output`.
- **Prova:** tutti i portafogli non vuoti, aggregato.
- **Difetto:** pesi calcolati su un totale che include la liquidità (somma < 100).

### D-SUMMARY-POSITIONS
- **Titolo:** Il riepilogo del portafoglio coincide con la somma delle posizioni
- **Sev.** P1 · **Area** values · **Finding** — (audit §E) · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_portfolio_summary")`, `scoped("get_positions")`.
- **Condizione:** `|market_value − Σ market_value delle righe| ≤ T_sum_eur(n)`;
  `|cost_basis − Σ cost_basis delle righe| ≤ T_sum_eur(n)`; `|unrealized_pl − (market_value −
  cost_basis)| ≤ 0,02 €`.
- **Tolleranze:** `T_sum_eur(n)` (righe arrotondate a 2 decimali; `cost_basis` di riga =
  `round(avg_cost × quantity, 2)` con `avg_cost` a 4 decimali, lo stesso prodotto del riepilogo);
  0,02 € per la differenza di due importi arrotondati.
- **Skip:** `empty_portfolio`; `truncated_output`.
- **Prova:** tutti i portafogli non vuoti, aggregato.
- **Difetto:** riepilogo che somma la liquidità nel `market_value`.

### D-POSITION-VALUE-PRICE
- **Titolo:** Il valore di ogni posizione è uguale a quantità per prezzo
- **Sev.** P2 · **Area** values · **Finding** V365-008 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_positions")`.
- **Condizione:** per ogni riga: `|market_value − quantity × market_price| ≤ T_eur + quantity ×
  0,00005 + 1e-6 × |market_value|`.
- **Tolleranze:** `market_price` arrotondato a 4 decimali (0,00005 per quota), `market_value` a 2.
- **Skip:** `empty_portfolio`.
- **Prova:** tutti i portafogli non vuoti, aggregato.
- **Difetto:** quantità divisa per mille con prezzo invariato.

### D-CASH-CONSISTENCY
- **Titolo:** La liquidità è la stessa nel riepilogo e nel saldo di cassa, e la sua scomposizione torna
- **Sev.** P1 · **Area** values · **Finding** C2-CASH-FX (TASK-47, TASK-49) · **Scope** portfolio
- **Tool:** `get_portfolio_summary`, `get_cash_balance`.
- **Condizione:** `|summary.cash_balance − total_cash| ≤ T_eur`;
  `|summary.implicit_contributions_total − cash.implicit_contributions_total| ≤ T_eur`;
  `total_cash ≥ 0`; `|Σ segno × cash_breakdown[k] − total_cash| ≤ 0,06 €` con segno +1 per
  `opening_balance`, `deposits`, `dividends`, `interest`, `sells`, `implicit_contributions` e −1 per
  `withdrawals`, `fees`, `buys` (`CASH_COMPONENT_SIGNS`); una chiave sconosciuta → `fail`.
- **Tolleranze:** `T_eur`; 0,06 € = nove componenti arrotondate a 2 decimali (`T_sum_eur(9)` = 0,055).
- **Skip:** nessuno (anche un portafoglio vuoto ha un saldo).
- **Prova:** tutti i portafogli, compreso 9106.
- **Difetto:** `get_cash_balance` al cambio più recente e riepilogo al cambio della data (prima di
  TASK-47), o riepilogo che ignora acquisti e vendite (prima di TASK-49).

### D-SUMMARY-PERFORMANCE-VALUE
- **Titolo:** Il valore totale del riepilogo coincide con l'ultimo valore usato per i rendimenti
- **Sev.** P1 · **Area** performance · **Finding** C1-TWR-MIXED, TASK-49 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_portfolio_summary")`, `scoped("get_positions")`, `ctx.transactions`
  (§0.3), `ctx.performance_audit(ids)`.
- **Condizione:** con V = `service_results.current_value` dell'export:
  `|market_value + cash_balance − V| ≤ 0,005 × (n + 2) + 1e-6 × |V|` (n = numero di posizioni:
  `len(positions)`, o `positions_count` nell'aggregato).
- **Tolleranze:** posizioni arrotondate a 2 decimali nel riepilogo, quantità a 8 decimali nella
  storia, liquidità e valore arrotondati. Una differenza di cambio nei giorni senza barra (cambio
  della data del prezzo nel riepilogo, cambio della data del valore nella storia) **non** va
  assorbita allargando la tolleranza: se compare è un difetto da tracciare (TASK-79).
- **Skip:** `no_transactions` (§0.3, controllato prima di leggere l'export).
- **Prova:** 9101, 9104, aggregato.
- **Difetto:** liquidità del riepilogo che non scala gli acquisti (esempio §9.1 della metodologia:
  1564,80 contro 1094,80).

### D-AGG-SUMS
- **Titolo:** La vista aggregata somma esattamente i portafogli che la compongono
- **Sev.** P1 · **Area** aggregate · **Finding** V365-011 · **Scope** aggregate
- **Tool:** `get_aggregate_summary`; `get_portfolio_summary` per ogni id.
- **Condizione:** per `market_value`, `cost_basis`, `cash_balance`, `implicit_contributions_total`:
  `|aggregato − Σ singoli| ≤ T_sum_eur(k)` con k portafogli; `aggregate.portfolio_ids` = gli id dello
  scope.
- **Tolleranze:** `T_sum_eur(k)`.
- **Skip:** nessuno (lo scope esiste solo con 2-20 portafogli).
- **Prova:** aggregato [9101…9107].
- **Difetto:** aggregazione manuale che conta due volte un portafoglio o salta la liquidità.

### D-AGG-POSITIONS
- **Titolo:** Le posizioni della vista aggregata uniscono quelle dei singoli portafogli
- **Sev.** P1 · **Area** aggregate · **Finding** V365-011 · **Scope** aggregate
- **Tool:** `get_aggregate_positions`; `get_positions` per ogni id.
- **Condizione:** per ogni riga aggregata: `|market_value − Σ market_value delle righe dei singoli con
  lo stesso symbol| ≤ T_sum_eur(k)` e `|quantity − Σ quantity| ≤ 1e-6 × k`; se nessun output è
  troncato: `positions_count` = numero di simboli distinti fra i singoli.
- **Tolleranze:** `T_sum_eur(k)`; quantità a 8 decimali.
- **Skip:** aggregato vuoto → `empty_portfolio`; righe di un singolo troncate e simbolo non trovato →
  `truncated_output` (solo per quella verifica).
- **Prova:** aggregato (`AUDEQ.MI` in quattro portafogli).
- **Difetto:** righe dello stesso strumento non unite (due righe `AUDEQ.MI`).

### D-AGG-PERFORMANCE-VALUE
- **Titolo:** Il valore finale della performance aggregata è la somma dei valori dei portafogli
- **Sev.** P2 · **Area** aggregate · **Finding** V365-011 · **Scope** aggregate
- **Tool:** `ctx.transactions` per ogni id (§0.3), `ctx.performance_audit(scope.portfolio_ids)`;
  `ctx.performance_audit([p])` per ogni id con transazioni.
- **Condizione:** `|current_value aggregato − Σ current_value singoli| ≤ T_sum_eur(k)` (campo
  `service_results.current_value`; i portafogli senza transazioni contano 0 e non si chiama l'export
  per loro, §0.3); `end_date` dell'aggregato uguale a quella di ogni singolo letto (le date di inizio
  possono differire: la finestra «1y» parte dalla prima transazione dello scope).
- **Tolleranze:** `T_sum_eur(k)`.
- **Skip:** nessuno.
- **Prova:** aggregato.
- **Difetto:** media dei valori invece della somma.

### D-PERF-RECOMPUTE
- **Titolo:** I rendimenti TWR e MWR coincidono con un ricalcolo indipendente
- **Sev.** P1 · **Area** performance · **Finding** C1-TWR-MIXED · **Scope** portfolio, aggregate · timeout 60 s
- **Tool:** `ctx.transactions` (§0.3), `ctx.performance_audit(ids)`;
  `app.services.auditor.offline_returns.audit(export,
  tolerance_pp=0.01)` (logica di `scripts/audit/twr_mwr_offline_auditor.py`).
- **Condizione:** `audit(...)["ok"] is True` (TWR e MWR di periodo entro `T_ret`, oppure entrambi
  null); `consistency_check.flows_match_service`, `count_match`, `totals_match` tutti veri.
- **Tolleranze:** `T_ret`.
- **Skip:** `no_transactions` come D-SUMMARY-PERFORMANCE-VALUE.
- **Prova:** 9101 (deposito e acquisti nella stessa finestra), 9104, aggregato.
- **Difetto:** acquisto non scalato dalla liquidità storica con un deposito nella finestra (deposito
  500, acquisto 10 × 100 a prezzo piatto → TWR +200% invece di 0%).

### D-PERF-TOOL-MATCH
- **Titolo:** Il rendimento mostrato è quello calcolato dal servizio
- **Sev.** P2 · **Area** performance · **Finding** C1-TWR-MIXED · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_performance")`; `ctx.transactions` (§0.3), `ctx.performance_audit(ids)`.
- **Condizione:** `|twr_1y − round(service_results.twr.twr_pct, 2)| ≤ T_pp` e
  `|mwr_1y − round(service_results.mwr.mwr_pct, 2)| ≤ T_pp`; un valore null solo se null anche
  nell'altro.
- **Tolleranze:** `T_pp`.
- **Skip:** `no_transactions`.
- **Prova:** 9101, aggregato.
- **Difetto:** tool che arrotonda o annualizza diversamente (periodo invece che annuo).

### D-DOCTOR-TER
- **Titolo:** Il TER medio è lo stesso nel Doctor, nella salute e nell'analisi dei costi
- **Sev.** P1 · **Area** doctor · **Finding** V365-007 (decisione 6) · **Scope** portfolio
- **Tool:** `read_doctor_metrics`, `get_portfolio_health`, `get_cost_breakdown`, `get_positions`,
  `search_asset_info` per riga.
- **Condizione:** con d = `value` della metrica `weighted_ter_pct`, h = `weighted_ter` della salute,
  c = `weighted_ter_pct` dei costi: `|d − c| ≤ 0,01` e `|h − c| ≤ 0,01`.
- **Tolleranze:** 0,01 pp (d e h a 2 decimali, c a 3).
- **Skip:** uno dei tre null → `no_reference_data`; una posizione con `type == "cash"` nella scheda
  (il Doctor la esclude dal valore investito, i costi no) → `not_applicable`; funzione spenta →
  `feature_disabled`.
- **Prova:** 9101, 9103.
- **Difetto:** TER del Doctor pesato sul totale invece che sul perimetro coperto.

### D-DOCTOR-CLASS-WEIGHTS
- **Titolo:** Le quote azionaria, obbligazionaria e oro del Doctor coincidono con lo stress test
- **Sev.** P1 · **Area** doctor · **Finding** V365-002 · **Scope** portfolio
- **Tool:** `read_doctor_metrics`, `get_stress_test`, `get_positions`.
- **Condizione:** pesi dello stress = `weight_pct` per classe del `class_breakdown` di «Global Equity
  Crash», rinormalizzati escludendo la classe `cash`: w'(c) = w(c) / (100 − w(cash)) × 100. Con
  `lower` delle metriche: `|equity_weight_pct.lower − w'(equity)| ≤ T_w(n)`,
  `|bond_weight_pct.lower − w'(bond)| ≤ T_w(n)`, `w'(gold) − T_w(n) ≤ gold_weight_pct.lower ≤
  w'(gold) + w'(commodity) + T_w(n)` (il Doctor conta con l'oro i metalli preziosi classificati
  commodity, `policy_asset_class`).
- **Tolleranze:** `T_w(n)` (pesi delle posizioni a 2 decimali nello stress, non arrotondati nel
  Doctor).
- **Skip:** `empty_portfolio`; funzione spenta → `feature_disabled`.
- **Prova:** 9101, 9102, 9103.
- **Difetto:** ETC sull'oro contato nell'azionario del Doctor ma non nello stress (o viceversa).

### D-DOCTOR-CONCENTRATION
- **Titolo:** Il peso della posizione più grande è lo stesso nel Doctor e nella salute
- **Sev.** P2 · **Area** doctor · **Finding** V365-010 · **Scope** portfolio
- **Tool:** `read_doctor_metrics`, `get_portfolio_health`.
- **Condizione:** con d = `value` di `max_single_position_pct` e h = `max_position_weight`: se le
  `notes` della metrica contengono «Stesso strumento (ISIN)» allora `d ≥ h − T_pp2`, altrimenti
  `|d − h| ≤ T_pp2`.
- **Tolleranze:** `T_pp2`.
- **Skip:** `empty_portfolio`; d null → `no_reference_data`; funzione spenta → `feature_disabled`.
- **Prova:** 9101, 9103.
- **Difetto:** concentrazione calcolata sul totale con la liquidità.

### D-HEALTH-SCORE-BREAKDOWN
- **Titolo:** Il punteggio di salute è la somma dei punteggi di categoria e delle penalità dichiarate
- **Sev.** P2 · **Area** doctor · **Finding** V365-010 · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_portfolio_health")`.
- **Condizione:** `score == Σ category_scores`; per ogni categoria k: `category_scores[k] ==
  max(0, category_max_scores[k] − Σ points delle score_deductions con category == k)`.
- **Tolleranze:** nessuna (interi).
- **Skip:** `empty_portfolio`.
- **Prova:** 9101, 9103, aggregato.
- **Difetto:** punti tolti senza una voce in `score_deductions`.

### D-XRAY-SUMS
- **Titolo:** Le esposizioni geografiche e settoriali sommano a cento
- **Sev.** P2 · **Area** values · **Finding** C6 (TASK-48) · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_xray_summary")`.
- **Condizione:** se `geographic_exposure` non è vuoto: `|Σ valori − 100| ≤ max(0,05; 0,005 × k)`
  con k bucket; idem `sector_exposure`; se `available_pct`, `not_applicable_pct`, `missing_pct` non
  sono null: `|somma − 100| ≤ 0,05`.
- **Tolleranze:** bucket a 2 decimali (residuo già assegnato al bucket maggiore nel servizio).
- **Skip:** `empty_portfolio`.
- **Prova:** 9101, 9103, aggregato (X-Ray offline: solo schede justETF del seed).
- **Difetto:** esposizioni sul totale con la liquidità (somma < 100) o senza «Non classificato».

### D-DUP-TRANSACTIONS
- **Titolo:** Non ci sono transazioni importate due volte
- **Sev.** P1 · **Area** data · **Finding** V365-009, V-DUP-IMPORT · **Scope** portfolio
- **Tool:** `ctx.transactions(portfolio_id)`.
- **Condizione:** raggruppa per (`asset_id`, `side`, `trade_date`, `trade_currency`) e, dentro il
  gruppo, per `quantity`, `price`, `fees` uguali con la regola di `_numbers_match` di
  `csv_service.py` (|x − y| ≤ max(1e-6 × max(|x|, |y|), 1e-8)). Fallisce se: un gruppo di lato di
  cassa (`deposit`, `withdrawal`, `dividend`, `fee`, `interest`) ha almeno 2 righe identiche, oppure
  un gruppo `buy`/`sell` ha almeno 3 righe identiche.
- **Tolleranze:** quelle della deduplica dell'import (stesso criterio dell'app).
- **Skip:** nessuna transazione → `no_transactions`.
- **Prova:** 9105 (coppia legittima di acquisti: nessun falso positivo), 9101, 9104.
- **Difetto:** stesso file confermato quattro volte (Wealth: 4 copie di 7 righe, dividendi gonfiati
  di 2.754,87 €). Limite: la tabella `transactions` non registra il lotto d'import, quindi «da import
  diversi» non è verificabile; una coppia di acquisti identici non è segnalata perché un'esecuzione
  frazionata è legittima (la stessa scelta della deduplica, TASK-42).

### D-TRADE-PRICE-SCALE
- **Titolo:** I prezzi delle operazioni importate sono sulla stessa scala del prezzo di mercato
- **Sev.** P1 · **Area** data · **Finding** V-XLSX-1000, V365-008, V-QUOTE-CCY-L · **Scope** portfolio
- **Tool:** `ctx.transactions(portfolio_id)`; `get_positions`.
- **Condizione:** per ogni transazione `buy`/`sell` il cui `symbol` ha una riga in `get_positions`
  con `price_fallback` null e `market_price > 0`: `price / market_price` in `R_px`.
- **Tolleranze:** `R_px`.
- **Skip:** `no_transactions`; nessuna transazione confrontabile → `no_reference_data`.
- **Prova:** 9101, 9104 (prezzi in USD e GBP contro prezzo di mercato in EUR).
- **Difetto:** cella XLSX letta come migliaia (prezzo 105.568 invece di 105,568; quantità ÷ 1000).

### D-LSE-QUOTE-CURRENCY
- **Titolo:** Gli strumenti quotati a Londra hanno una valuta di quotazione plausibile
- **Sev.** P1 · **Area** data · **Finding** V-QUOTE-CCY-L, V365-008 · **Scope** instrument
- **Tool:** `search_asset_info`.
- **Condizione:** se `scope.symbol` termina con `.L` (senza distinzione di maiuscole): `currency` ∈
  {`GBP`, `GBp`, `GBX`, `USD`}.
- **Tolleranze:** nessuna.
- **Skip:** simbolo senza `.L` → `not_applicable`.
- **Prova:** `AUDUS.L`, `AUDUK.L` in 9104.
- **Difetto:** `quote_currency` = valuta base del portafoglio alla creazione dell'asset (tutti i `.L`
  in EUR). Limiti: `search_asset_info` non espone borsa né simbolo del provider, quindi un listing di
  Londra salvato senza suffisso (es. `VWRA` con simbolo Yahoo `VWRA.L`) non è riconosciuto; esistono
  linee in EUR alla LSE, rare nei portafogli dell'app (se un caso reale emerge si aggiunge
  un'eccezione esplicita per ISIN). Probabile **difetto noto sui dati di produzione** finché TASK-41 è
  aperto.

### D-FX-FLAGS-DECLARED
- **Titolo:** Prezzi fermi, prezzi mancanti e cambi mancanti sono segnalati nel riepilogo
- **Sev.** P2 · **Area** values · **Finding** C4-FX-FALLBACK (TASK-47, TASK-53) · **Scope** portfolio, aggregate
- **Tool:** `scoped("get_portfolio_summary")`, `scoped("get_positions")`.
- **Condizione:** simboli delle righe con `price_fallback == "avg_cost"` = `price_fallback_symbols`
  del riepilogo; simboli con `price_stale` vero = `stale_price_symbols`; una riga con `fx_missing`
  vero ⇒ `fx_missing_currencies` non vuoto; una delle tre liste non vuota ⇒ `data_quality_note`
  presente. Con righe troncate le uguaglianze diventano inclusioni (righe ⊆ riepilogo).
- **Tolleranze:** nessuna.
- **Skip:** `empty_portfolio`.
- **Prova:** 9107 (prezzo fermo), tutti gli altri (liste vuote e coerenti).
- **Difetto:** prezzo ripiegato sul costo medio senza segnalazione.

### D-HELD-SYMBOL-MATCH
- **Titolo:** La scheda di uno strumento in portafoglio si riferisce proprio a quel listing
- **Sev.** P2 · **Area** data · **Finding** V-LOOSE-SYMBOL · **Scope** instrument
- **Tool:** `search_asset_info` `{"symbol": scope.symbol}`.
- **Condizione:** `match == "portfolio"`, nessun `warning`, `symbol` uguale a `scope.symbol` senza
  distinzione di maiuscole.
- **Tolleranze:** nessuna.
- **Skip:** nessuno.
- **Prova:** tutti gli strumenti del seed.
- **Difetto:** risoluzione per ticker base (`XAD1.DE` che risolve su un altro listing).

## 6. Difetti noti (TASK-79)

Regole che falliscono sul codice o sui dati attuali perché trovano un difetto reale. La regola resta
attiva con `known_defect` nella dichiarazione.

| regola | difetto | task | dal |
|---|---|---|---|
| — | — | — | — |

## 7. Copertura dei finding di novembre

### 7.1 Finding P0 e P1

| finding | sev. | regole | note |
|---|---|---|---|
| V365-001 stress storici identici | P0 | A-STRESS-HIST-DISTINCT, A-STRESS-PROXY-TABLE, A-STRESS-METHOD-COVERAGE, A-STRESS-CONTRIB-SUM | |
| V365-002 shock azionario su bond/oro/commodity | P0 | A-STRESS-SHOCK-TABLE, A-STRESS-NONEQUITY-POSITION-SHOCK, A-CLASS-STRESS-CONSISTENT, D-DOCTOR-CLASS-WEIGHTS, A-CLASS-UNKNOWN-DECLARED (decisione 3) | |
| V365-003 ribilanciamento senza autofinanziamento | P0 | B-REB-CASH-CONSERVATION, B-REB-CASH-NONNEG, B-REB-SELLS-REACH-TARGET, B-REB-DRIFT-NONINCREASING, B-REB-MODE-SIDES, B-REB-SELL-CAP | |
| V365-004 ETF obbligazionari come azionari nel reddito | P1 | C-INCOME-CLASS-RECOMPUTE, C-INCOME-BUCKETS-SUM | |
| V365-005 day movers null | P1 | C-DAYMOVERS-NONZERO-INCLUDED, C-DAYMOVERS-CONSISTENCY | |
| V365-006 anno 10 del Monte Carlo | P1 | C-MC-YEARS, C-MC-PERCENTILES, C-MC-MEDIAN-DRIFT | |
| V365-007 TER incompleti presentati come completi | P1 | C-COST-COHERENCE, C-COST-COVERAGE-DECLARED, C-TER-RANGE, D-DOCTOR-TER, A-CLASS-ETP-TER-NONZERO | |
| V365-008 prezzi di carico e valuta (SE15, IBTM) | P1 | causa 1: D-TRADE-PRICE-SCALE, D-POSITION-VALUE-PRICE; causa 2: D-LSE-QUOTE-CURRENCY | il costo medio di righe miste (corrette ed errate) non è verificabile come invariante: lo è ogni singola riga |
| V365-009 dividendi ripetuti | P1 | D-DUP-TRANSACTIONS, C-DIV-CURRENCY (conteggio) | coppie di acquisti identici non segnalate (vedi scheda) |
| V-TER-UNIT | P1 | C-TER-RANGE | |
| V-INCOME-TYPE | P1 | C-INCOME-CLASS-RECOMPUTE | |
| V-DAYMOVERS-ROOT | P1 | C-DAYMOVERS-NONZERO-INCLUDED, C-DAYMOVERS-CONSISTENCY | «variazione assente non riportata come zero» è verificabile solo su `get_day_movers`: `get_positions` riporta 0 per una posizione senza chiusura precedente e non espone `previous_close_available` (§9) |
| V-XLSX-1000 | P1 | D-TRADE-PRICE-SCALE | |
| V-DUP-IMPORT | P1 | D-DUP-TRANSACTIONS | |
| V-FINECO-FEES | P1 | **nessuna** | non è un'invariante: dire se il prezzo dell'export comprende già la commissione richiede l'estratto conto del broker (decisione aperta, TASK-45). Un indizio (quantità non intere vicine a un intero, prezzo diverso dalle righe gemelle di una quantità pari a fees / quantità) dà falsi positivi su frazioni e prezzi reali; resta un tema per l'agente settimanale e per un test dell'import Fineco |
| V-QUOTE-CCY-L | P1 | D-LSE-QUOTE-CURRENCY, D-TRADE-PRICE-SCALE | pence letti come sterline escono da `R_px` |
| C1-TWR-MIXED | P1 | D-PERF-RECOMPUTE, D-SUMMARY-PERFORMANCE-VALUE, D-PERF-TOOL-MATCH | |
| TASK-49 liquidità del riepilogo contata due volte (priorità alta, senza id di finding) | — | D-SUMMARY-PERFORMANCE-VALUE, D-CASH-CONSISTENCY | |

### 7.2 Finding P2 e controlli della sezione C

| finding | regole o motivo |
|---|---|
| V365-010 score e volatilità | D-HEALTH-SCORE-BREAKDOWN, D-DOCTOR-CONCENTRATION; i metadati della volatilità (`is_floored`, nome, metodo) sono descrittivi, non invarianti numeriche |
| V365-011 aggregazioni | D-AGG-SUMS, D-AGG-POSITIONS, D-AGG-PERFORMANCE-VALUE (e le regole con scope `aggregate`) |
| V365-012 ETC oro come azione | A-CLASS-ETC-NOT-EQUITY, A-CLASS-ETP-TER-NONZERO, A-CLASS-STRESS-CONSISTENT |
| V365-013, V-HEAVY-QUOTA limiti MCP | non coperti: concorrenza e quote sono in `_run_bounded`, che l'Auditor non attraversa per scelta (§0 dell'architettura); restano coperti da `tests/unit/test_mcp_tool_limits.py` |
| V-DIV-MIXED-CCY | C-DIV-CURRENCY |
| V-LOOSE-SYMBOL | D-HELD-SYMBOL-MATCH |
| V-BOND-QUOTETYPE | A-CLASS-BOND-TYPE (solo stato salvato) |
| C2-CASH-FX | D-CASH-CONSISTENCY |
| C3 `day_change` del riepilogo contro le posizioni | nessuna regola: differenza attesa e documentata (prezzi non arrotondati, FX corrente e precedente) |
| C4-FX-FALLBACK | D-FX-FLAGS-DECLARED |
| C4-CCY `currency` di `search_asset_info` | D-LSE-QUOTE-CURRENCY |
| C5 reddito contro rendimento totale | nessuna regola: limite del modello dichiarato (`missing_yield_symbols`) |
| C6 X-Ray | D-XRAY-SUMS |
| C7 nota fiscale | nessuna regola: testo descrittivo; C-INCOME-BUCKETS-SUM verifica il netto con l'aliquota dichiarata |
| C8 quantità frazionarie | nessuna regola: tolleranza contabile non decisa (decisione aperta) |
| invarianti contabili e di simulazione senza finding (§E del brief originale) | D-WEIGHTS-SUM, D-SUMMARY-POSITIONS, B-PAC-SUM, B-PAC-UNDERWEIGHT-ONLY, B-WHATIF-BUY-WEIGHT, B-WHATIF-SELL-BOUND |

## 8. Regole valutate e non incluse

- **Scenario Lab** (`build_doctor_scenario`, `compare_doctor_scenarios`): le invarianti di capitale
  sono già testate in `services/doctor_policy/scenario.py` e l'input richiede scenari costruiti per
  portafoglio; candidate per un secondo giro (proposte dall'agente settimanale).
- **Soglie euristiche dell'health score** (USA > 60%, TER > 0,75%…): sono scelte di prodotto, non
  invarianti; D-HEALTH-SCORE-BREAKDOWN verifica solo che i punti tornino.
- **Freschezza globale dei prezzi** (`data_freshness`): dipende dall'ora della corsa e dalla
  sincronizzazione, non dai calcoli; è già monitorata dal workflow di sincronizzazione.

## 9. Incoerenze fra task e codice rilevate scrivendo il catalogo

- **TASK-76** chiede percentili «p10 ≤ p50 ≤ p90»: `get_monte_carlo` espone solo `p25`, `p50`,
  `p75` (P10/P90 esistono nel servizio ma il tool non li restituisce). Il catalogo usa P25/P50/P75.
- **Metodologia §5** dice che `total_annual_cost_eur` è null con copertura incompleta: il codice
  restituisce lo stesso valore di `estimated_annual_cost_known_eur` (chiave legacy). C-COST-COHERENCE
  segue il codice; la discrepanza è della documentazione.
- **`get_positions`** non espone `previous_close_available`: una posizione senza chiusura precedente
  mostra `day_change_pct` 0 (rischio residuo n. 10 di `regression-results.md`).
- **`get_stress_test`** non espone l'id dello scenario: le regole mappano per nome (§0.3).
- **`get_aggregate_performance_audit`** esiste solo per 2-20 portafogli: per il singolo il contesto
  chiama la stessa funzione (`ctx.performance_audit`, architettura §5.4).
- **`get_recent_transactions`** restituisce solo 20 righe e la tabella `transactions` non ha l'id del
  lotto d'import: duplicati e prezzi d'import richiedono `ctx.transactions` e il criterio «righe
  identiche».
- **`calculate_pac_contribution`**: con nessuno strumento sottopesato la distribuzione è vuota ma
  `total_allocated` vale l'importo (B-PAC-SUM lo segnala).
- **TASK-78** parla di «tentativo di import duplicato»: un seed SQL non passa dal flusso d'import;
  il caso è rappresentato come in §1.
