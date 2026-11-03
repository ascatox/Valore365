# Valore365 — Rapporto di retest delle anomalie via MCP

**Data del retest:** 3 novembre 2026  
**Baseline di confronto:** audit MCP precedente, 2 novembre 2026  
**Repository:** `ascatox/Valore365`  
**Finalità:** verificare, dopo numerosi fix, quali criticità dell'audit precedente sono chiuse e quali richiedono ulteriori interventi.

> **Nota fondamentale sulla provenienza dei risultati:** tutti i risultati numerici e gli output applicativi riportati in questo documento provengono da chiamate reali ai tool del **server MCP di Valore365**, effettuate dall'assistente ChatGPT con il connettore Valore365 autenticato in **sola lettura**. Non sono risultati inventati, né test simulati dall'assistente, né valori dedotti dalle sole descrizioni del codice. Quando il documento cita possibili cause nel sorgente, queste provengono da **lettura separata del repository GitHub** e sono indicate come tali. Nessun test di questo audit ha modificato portafogli, ordini o transazioni.

## 1. Metodo e limiti

### Modalità di esecuzione

1. Eseguito `list_portfolios` sul connettore MCP per ottenere gli ID autorizzati.
2. Chiamati i tool MCP di lettura e analisi sui quattro portafogli restituiti.
3. Confrontati gli output del 3 novembre con le osservazioni documentate nel precedente audit del 2 novembre.
4. Verificati gli invarianti aritmetici confrontando i valori ricevuti da più tool MCP.
5. **Separatamente dall'MCP**, letti alcuni file di implementazione su GitHub per interpretare i risultati e formulare ipotesi sulla causa.

### Portafogli interrogati via MCP

| `portfolio_id` | Nome | Valuta |
|---:|---|---|
| 19 | Parent | EUR |
| 26 | Wealth | EUR |
| 24 | All Weather | EUR |
| 33 | 100 % Azionario Globale | EUR |

**Avvertenza:** Parent e Wealth restano portafogli separati nel database; eventuali totali aggregati sono solo calcoli analitici. All Weather e 100% Azionario non devono essere automaticamente considerati parte del patrimonio personale reale.

### Tool MCP effettivamente utilizzati nel retest

- `list_portfolios`
- `get_portfolio_summary`
- `get_positions`
- `get_portfolio_health`
- `get_stress_test`
- `get_day_movers`
- `get_dividend_summary`
- `get_cost_breakdown`
- `get_monte_carlo`
- `calculate_rebalance_orders`
- `get_income_projection`
- `get_recent_transactions`
- `get_performance`
- `get_xray_summary`
- `search_asset_info`

**Limiti importanti:** i tool restituiscono uno snapshot e non sostituiscono estratti conto del broker; `get_recent_transactions` espone al massimo 20 movimenti; non è stata eseguita una suite CI locale né una riconciliazione completa dei movimenti storici contro documenti indipendenti. I test mostrano il comportamento della connessione MCP disponibile in questa sessione, non necessariamente di ogni altra installazione o client.

## 2. Esito sintetico delle 13 criticità originali

| ID | Criticità | Esito dopo i fix | Evidenza via MCP / limitazione |
|---|---|---|---|
| V365-001 | Stress test storici uguali per composizioni diverse | **Risolto nel comportamento osservato** | I drawdown del 2008 ora differiscono: Parent -40,02%; Wealth -32,51%; All Weather -19,26%; 100% Azionario -54,00%. |
| V365-002 | Shock assegnati a classi finanziarie errate | **Parziale** | Scenari diversificati per classi, ma `DBXP.DE` resta `unknown` e riceve shock equity; `VEUR` è `unknown`. |
| V365-003 | Ribilanciamento vende senza finanziare gli acquisti | **Risolto nel test** | In `calculate_rebalance_orders(available_cash=0)` vendite = acquisti, `cash_after=0`, `invariant_ok=true`. |
| V365-004 | ETF obbligazionari classificati come azionari nel reddito | **Risolto nel test** | `get_income_projection`: Parent fixed income 568,94 €, Wealth 935,65 €. |
| V365-005 | `get_day_movers` restituisce `null` | **Risolto nel test** | Parent e Wealth hanno best/worst; il tool espone anche esclusioni per prezzi stale. |
| V365-006 | Monte Carlo si arresta all'anno 9 | **Risolto nel test** | Tutti i quattro portafogli restituiscono gli anni da 1 a 10; unità dichiarata come indice base 100. |
| V365-007 | Costi/TER incompleti presentati senza avviso | **Risolto per trasparenza** | Esposti `ter_coverage_pct`, `missing_ter_symbols` e perimetro dei costi; restano dati mancanti. |
| V365-008 | Quantità e costi di carico sospetti | **Parziale / non verificabile senza broker** | Cambiamenti sostanziali in Wealth; valori interni quadrano, ma non riconciliati con operazioni originali. |
| V365-009 | Dividendi apparentemente duplicati | **Risolto nei dati visibili** | Duplicati prima visibili non presenti nelle ultime 20 transazioni; da 64 a 46 movimenti dividendo storici per Wealth. |
| V365-010 | Health Score e volatilità poco spiegabili | **Risolto per trasparenza** | Score per categoria, deduzioni e descrizioni delle diverse volatilità esposti. |
| V365-011 | MCP non permette aggregazione multi-portafoglio | **Parziale / versione client da verificare** | Tool aggregati presenti nel codice GitHub, ma assenti dal catalogo invocabile in questa connessione ChatGPT. |
| V365-012 | ETC oro XAD1 indicato come `stock` | **Ancora presente nell'output** | `search_asset_info(XAD1.DE)` restituisce `type=stock`; altre analisi lo riconoscono come oro. |
| V365-013 | Rate limit ed errori di esecuzione | **Non riprodotto nel retest** | Chiamate di analisi completate; i limiti dichiarati restano intenzionali, non è stata fatta una prova di carico. |

## 3. Evidenze precise sui problemi non completamente chiusi

### V365-002 — Classificazione negli stress test — **PARZIALE**, priorità alta

**Riproduzione via MCP:**

- `get_stress_test(portfolio_id=19)` restituisce `DBXP.DE` (`XTR2 EGB13 1CC`, ISIN `LU0290356871`) con `asset_class="unknown"`.
- DBXP rappresenta circa **6,39%** di Parent, **15.668,55 €**.
- Nello scenario `US Tech Crash`, tra gli asset più colpiti DBXP riceve `loss_pct=-30`, come se fosse un'azione. Nel breakdown dello scenario, la classe `bond` riceve invece lo shock ipotetico `+2`.
- Lo stesso tool sul portafoglio 33 restituisce `VEUR` (ETF azionario europeo) come `unknown`.
- La risposta ora contiene `flags`, `class_breakdown` e contributi; questa trasparenza è un miglioramento, ma **non corregge la classificazione errata**.

**Impatto potenziale sull'esempio Parent:** se DBXP ricevesse *per sola illustrazione* lo shock del bucket bond (+2%) invece del fallback equity (-30%), la differenza sul portafoglio sarebbe circa `6,39% × 32 punti = 2,04 punti percentuali`. **Non** è una previsione di come DBXP si comporterebbe realmente.

**Riscontro distinto nel codice GitHub:** `src/backend/app/services/asset_classification.py` classifica usando metadata, stringhe dei nomi, simboli e alcuni ISIN; i nomi abbreviati `XTR2 EGB13 1CC` e `Azioni Europa` possono non essere riconosciuti dalle regole correnti. `src/backend/app/services/portfolio_doctor/_holdings.py` passa informazioni degli strumenti al classificatore.

**Azioni per l'agente:**

1. Riprodurre su fixture con ISIN di DBXP e VEUR, preservando i nomi abbreviati.
2. Diagnosticare perché le fonti metadata e i suggerimenti non attribuiscono `bond` a DBXP e `equity` a VEUR.
3. Preferire metadati strutturati e identificazione per ISIN, con fallback motivato; evitare di affidarsi solo ad alias hardcoded o regex.
4. Verificare tutti i consumer del classificatore: stress, income, X-Ray, Health.
5. Test di accettazione: `DBXP.DE -> bond`, `VEUR -> equity` negli scenari e nei riepiloghi; breakdown numerico coerente.

### V365-008 — Quantità, costi di carico e rendimento Wealth — **PARZIALE**, priorità molto alta

**Confronto di due letture MCP (prima/dopo fix):**

| Metrica Wealth | 2 novembre | 3 novembre | Differenza |
|---|---:|---:|---:|
| Valore posizioni | 417.257,89 € | 433.791,57 € | +16.533,68 € |
| Costo di carico | 362.200,67 € | 352.063,99 € | -10.136,68 € |
| Plusvalenza non realizzata | 55.057,22 € | 81.727,58 € | +26.670,36 € |
| Liquidità restituita | 819,59 € | 0 € | -819,59 € |
| TWR YTD | 20,22% | 5,63% | -14,59 pp |
| TWR 1 anno | 35,22% | 7,64% | -27,58 pp |

**Quantità Wealth cambiate:**

| Ticker | Prima (circa) | Dopo (circa) |
|---|---:|---:|
| VWRA.L | 870,06 | 930,00 |
| SE15.L | 477,03 | 506,00 |
| IBTM.L | 49,04 | 92,00 |
| EUN5.DE | 315,02 | 242,00 |

Nei due snapshot i prezzi restituiti per gli strumenti condivisi erano invariati, mentre quantità e costo di carico erano cambiati. **Questo non dimostra un bug**, perché possono essere stati corretti import, calcoli o movimenti, ma richiede una riconciliazione documentata.

**Modello cash osservato via MCP:** `get_portfolio_summary` restituisce `cash_balance=0` e `implicit_contributions_total=194.619,44 €` su Parent, `346.688,20 €` su Wealth, con una nota che spiega gli apporti impliciti per coprire acquisti o uscite non finanziati dalla liquidità registrata.

**Controlli che passano:** la somma delle posizioni coincide con `summary.market_value` su tutti i 4 portafogli; somma dei costi a un centesimo; `market_value-cost_basis=unrealized_pl`.

**Da verificare prima di chiudere:**

1. Ricostruire quantità e prezzo medio residuo da **tutti** gli acquisti, vendite, trasferimenti, commissioni, imposte e corporate action.
2. Riconciliare con estratti conto broker/posizioni ufficiali, non soltanto con un altro servizio che usa lo stesso DB.
3. Documentare il ruolo degli apporti impliciti e il loro effetto su TWR/MWR.
4. Creare test con flussi mancanti, vendite parziali, modifiche allo storico e ricalcolo dei costi.
5. Non correggere dati reali a mano per ottenere il valore atteso.

### V365-011 — Aggregazione MCP — **PARZIALE**, priorità media

**Osservazione via MCP/client:** la lista degli strumenti Valore365 invocabili in questa connessione contiene solo tool con un singolo `portfolio_id`, più `list_portfolios`. **Non sono disponibili qui** `get_aggregate_summary`, `get_aggregate_positions` e gli altri tool `get_aggregate_*`.

**Riscontro distinto su GitHub:**

- `src/backend/app/mcp_server/aggregate_tools.py` definisce nove tool `get_aggregate_*` con `portfolio_ids`.
- `src/backend/app/mcp_server/tools.py` registra i tool tramite `AGGREGATE_TOOLS.values()` e li instrada verso `_run_aggregate_tool`.
- Il codice dichiara vista aggregata in sola lettura e controllo di ownership per ogni portafoglio.

**Possibili cause non ancora discriminate:** deploy MCP non aggiornato, catalogo del connettore ChatGPT non aggiornato, differenza di versione/schema tra server e connessione o errore nella registrazione dei tool.

**Test di chiusura:**

1. Richiedere `tools/list` all'endpoint MCP di produzione usando un client autorizzato/MCP Inspector, registrando commit/versione.
2. Verificare la presenza dei nove tool aggregati ed eventualmente ricreare o aggiornare il connettore ChatGPT.
3. Eseguire `get_aggregate_summary` e `get_aggregate_positions` con `portfolio_ids=[19,26]`.
4. Per lo snapshot del 3 novembre, il valore complessivo **delle posizioni** Parent+Wealth è **678.815,88 €**, costo complessivo **546.859,12 €**, plusvalenza **131.956,76 €**; confrontare con il risultato aggregato **solo a parità di snapshot**.
5. Eseguire `get_aggregate_stress_test`: non limitarsi alla somma aritmetica dei drawdown singoli se il motore considera correlazioni/esposizioni aggregate.
6. Testare ID non autorizzati, valute diverse, ID duplicati e garanzia di sola lettura.

**Non dichiarare** che il server non possiede i tool: l'osservazione dimostra solo che questa connessione non li espone.

### V365-012 — Tipo di XAD1.DE — **ANCORA PRESENTE NELL'OUTPUT**, priorità medio-bassa

**Riproduzione via MCP:**

`search_asset_info(portfolio_id=26, symbol="XAD1.DE")` restituisce:

```json
{
  "symbol": "XAD1.DE",
  "name": "GOLD/DB ETC 60",
  "type": "stock",
  "currency": "EUR",
  "isin": "DE000A1EK0G3"
}
```

Lo strumento è un ETC collegato all'oro. **La classificazione finanziaria downstream non risulta necessariamente errata**: l'X-Ray distingue l'oro dalle azioni e il classificatore nel repository contiene indizi per `XAD1` e l'ISIN.

**Riscontro distinto nel codice GitHub:** `_search_asset_info` in `src/backend/app/copilot_tools.py` usa `asset_detail.asset_type` per compilare `type`; `src/backend/app/services/asset_classification.py` distingue questo tipo tecnico dalla classe finanziaria `gold`.

**Soluzione proposta, senza migrazione indiscriminata del DB:**

- Esportare due proprietà diverse: il tipo tecnico memorizzato (`asset_type`) e la classe di rischio/esposizione (`asset_class`); se determinabile con affidabilità, anche `instrument_type="etc"` e origine della classificazione.
- Chiarire quale proprietà deve usare un LLM per asset allocation, X-Ray, stress e income.
- Test su XAD1, ETF azionario, ETF obbligazionario, ETN e azione singola.
- La criticità è chiusa quando l'output MCP non permette più di confondere l'ETC sull'oro con un'azione; **non** è necessario riscrivere il dato storico `assets.asset_type` se rappresenta una convenzione tecnica deliberata.

## 4. Altre verifiche da non perdere

### Freschezza delle quotazioni

Il 3 novembre `get_day_movers` riportava per le posizioni Parent/Wealth `price_date="2026-10-30"`. Anche le quotazioni `get_positions` coincidevano con la lettura precedente. Verificare scheduler, calendario dei mercati, timezone, timestamp di ultima sincronizzazione e criterio per `excluded_stale`. **Non** è stato dimostrato un malfunzionamento del provider.

### Copertura TER

`get_cost_breakdown` mostra ora esplicitamente:

| Portafoglio | Copertura TER | Titoli mancanti |
|---|---:|---|
| Parent | 100,0% | Nessuno |
| Wealth | 95,0% | XAD1.DE |
| All Weather | 34,9% | TLT, IEF, DJP, GLD |
| 100% Azionario | 75,4% | VEUR |

**Bug di trasparenza risolto**; resta incompleta la raccolta dei TER per alcuni strumenti.

### X-Ray

`get_xray_summary` mostra copertura dei sottostanti pari a:

- Parent: 87,6%;
- Wealth: 84,7%;
- All Weather: 0%;
- 100% Azionario: 14,2%.

La copertura parziale viene segnalata, ma limita significativamente l'affidabilità delle analisi look-through su alcuni portafogli. Strumenti come oro e commodity non devono avere necessariamente top holdings azionarie: distinguere **non applicabile** da **dati mancanti**.

### Dividendi Wealth

`get_dividend_summary` passa da 64 movimenti dividendo e 6.876,59 € dell'audit precedente a 46 movimenti e 4.121,72 € nello snapshot attuale. La finestra di `get_recent_transactions` non mostra più le ripetizioni identiche dei dividendi IHYG ed EQQQ segnalate in precedenza. Questo è un segnale positivo, **non** una riconciliazione completa dei pagamenti originali.

### Natura modellistica degli stress storici

I nuovi stress test differenziano i portafogli, ma gli scenari storici osservati indicano `method="proxy"` e `coverage_pct=0`; la risposta spiega anche che i proxy usano drawdown di indici in USD e non incorporano necessariamente l'effetto EUR/USD. Non interpretarli come ricostruzioni storiche precise del singolo ETF.

## 5. Checklist operativa per un agente di coding

- [ ] **P1 — DBXP e VEUR:** scrivere test che riproducono `unknown`; correggere classificatore/metadata; rivalidare stress, income e X-Ray.
- [ ] **P1 — Wealth:** confrontare quantità finali e TWR con lo storico completo del broker; documentare apporti impliciti e differenze post-fix.
- [ ] **P2 — MCP aggregato:** confrontare `tools/list` di produzione con catalogo del client; invocare aggregati dopo refresh.
- [ ] **P2 — XAD1:** chiarire `asset_type`, `asset_class`, `instrument_type` nella risposta `search_asset_info`; testare coerenza downstream.
- [ ] **P2 — Quote stale:** verificare freschezza, sessione di borsa e cache prezzi.
- [ ] **P2 — X-Ray/TER:** riportare copertura e missing vs not-applicable; estendere enrichment solo da fonti verificabili.
- [ ] Rieseguire la suite di regressione e annotare commit, test verdi, test falliti, limitazioni e decisioni finanziarie ancora aperte.

### Condizioni di chiusura

Una voce non si considera chiusa perché esiste una patch o un test unitario isolato. Richiedere **sia**:

1. evidenza del comportamento corretto nei test del codice;
2. verifica end-to-end dell'output MCP, sulla versione effettivamente deployata;
3. nei casi di contabilità finanziaria, confronto con dati indipendenti del broker.

## 6. Riferimenti tecnici (letti su GitHub, non via MCP)

- [`src/backend/app/copilot_tools.py`](https://github.com/ascatox/Valore365/blob/main/src/backend/app/copilot_tools.py)
- [`src/backend/app/services/asset_classification.py`](https://github.com/ascatox/Valore365/blob/main/src/backend/app/services/asset_classification.py)
- [`src/backend/app/services/portfolio_doctor/_holdings.py`](https://github.com/ascatox/Valore365/blob/main/src/backend/app/services/portfolio_doctor/_holdings.py)
- [`src/backend/app/mcp_server/tools.py`](https://github.com/ascatox/Valore365/blob/main/src/backend/app/mcp_server/tools.py)
- [`src/backend/app/mcp_server/aggregate_tools.py`](https://github.com/ascatox/Valore365/blob/main/src/backend/app/mcp_server/aggregate_tools.py)

---

**Conclusione dell'audit:** i fix hanno risolto numerosi problemi precedentemente osservati. I risultati qui descritti sono **evidenze da chiamate reali via MCP**, integrate soltanto dove espressamente indicato con ispezione del codice GitHub. Le principali verifiche residue riguardano classificazione degli strumenti, riconciliazione quantità/rendimenti, disponibilità dei tool aggregati nel client e semantica dell'anagrafica dell'ETC oro.
