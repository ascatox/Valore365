# Auditor dei calcoli — portafogli di prova

| file | cosa fa |
|---|---|
| `audit_seed.sql` | seed dell'Auditor (TASK-78): utente `auditor-seed-user`, portafogli 9101-9107 in EUR, 13 strumenti fittizi `AUD*` (id 9101-9113), prezzi, storico degli stress test, cambi EUR/USD ed EUR/GBP, TER, schede justETF e metadati yFinance. Date relative a `current_date`, nessuna rete. |
| `agent_stack.sh` | stack locale usa e getta per l'agente settimanale (TASK-82): Postgres 16 su socket Unix, schema, migrazioni e seed; `start` (idempotente, stampa `DATABASE_URL=...`), `url`, `env`, `status`, `reseed`, `stop`. Variabili `PG_BIN`, `AGENT_DIR`, `PG_PORT`, `DB_NAME`. |
| `mcp_call.py` | chiama un tool del server MCP in processo come `auditor-seed-user`, senza Clerk, finance client offline, solo database locali; argomenti JSON, risultato JSON; `--list`, `--schema TOOL`, `--batch FILE.jsonl`, `--save`, `--debug`. |

Contratto: `docs/auditor/rules.md` §1 (portafogli, strumenti, regole esercitate) e
`docs/auditor/architecture.md` §6 e §9 (CI su Postgres effimero, determinismo, provider offline).
Test: `src/backend/tests/integration/test_auditor_seed_postgres.py`.

## Come si applica

Dopo `database/schema.sql` e tutte le migrazioni di `database/migrations/`, in ordine:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/schema.sql
for f in database/migrations/*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/auditor/audit_seed.sql
```

Lo script è una sola transazione ed è riapplicabile: cancella prima i portafogli 9101-9107 (e ogni
portafoglio di `auditor-seed-user`), gli strumenti 9101-9113 e i cambi con provider `auditor-seed`.
Le sequenze non vengono toccate. Si applica anche accanto a `scripts/e2e/doctor2_seed.sql` (id 1-5).

## Determinismo

- Prezzi recenti con una formula in `n` = giorni prima di oggi
  (`base × (1 − drift·n) × (1 + amp·(sin(n/9 + fase) − sin(fase)))`): la barra più recente vale
  esattamente `base`, quella del giorno prima è diversa. Stessa formula, stessi numeri ogni giorno.
- Storico degli stress test su date fisse (finestre di `HISTORICAL_SCENARIOS`): barre settimanali
  più l'ultimo giorno della finestra, prezzo lineare, rendimento della finestra scelto per strumento.
- Cambi giornalieri per 401 giorni (`fx_rates_1d`, `rate` = EUR per unità di valuta): oggi
  USD 0,92 e GBP 1,17 esatti.
- Transazioni alle 12:00 dei giorni relativi a oggi; dividendi come `quantity 1 × price`.
- Nessun tick (`price_ticks` vuota per gli strumenti del seed): la chiusura precedente è la barra
  del giorno prima.
- Una riga in `market_data_sync_runs` (sincronizzazione riuscita 20 minuti prima): solo per il blocco
  `data_freshness`, non entra nei calcoli.

Non dipendono dalla data i valori di oggi (prezzi, cambi, quantità, liquidità, pesi), gli esiti
degli stress test, costi, reddito e dividendi. Monte Carlo e volatilità sono deterministici a parità
di giorno (seed 42), ma non sono documentati come numeri fissi.

## Strumenti

| id | simbolo | tipo | valuta | prezzo oggi | dati nel seed | classe (`search_asset_info`) |
|---|---|---|---|---|---|---|
| 9101 | `AUDEQ.MI` | etf | EUR | 100,00 | justETF «Equity, World», TER 0,22, pesi paese (USA 62, Giappone 5,5, Regno Unito 3,5, Altri 29) | equity / etf |
| 9102 | `AUDBD.MI` | etf | EUR | 50,00 | justETF «Bonds, World, Aggregate», TER 0,10 | bond / etf |
| 9103 | `AUDTECH.DE` | etf | EUR | 200,00 | justETF «Equity, United States, Technology», TER 0,30; dividend_yield 0,6 | equity / etf |
| 9104 | `AUDGOV.MI` | etf | EUR | 120,00 | justETF «Bonds, Euro, Government», TER 0,15; dividend_yield 2,5 | bond / etf |
| 9105 | `AUDHY.DE` | **stock** | EUR | 95,00 | nessuna scheda; metadati: category «High Yield Bond», expense_ratio 0,005, dividend_yield 5,0 | bond / etf |
| 9106 | `AUDBTP` | **bond** | EUR | 101,00 | nessuna scheda; dividend_yield 1,6 | bond / bond |
| 9107 | `AUDGLD.DE` | **stock** | EUR | 40,00 | justETF «Precious Metals, Gold», TER 0,25 | gold / etc |
| 9108 | `AUDCMD.MI` | etf | EUR | 20,00 | justETF «Commodities, Broad market», TER 0,19 | commodity / etf |
| 9109 | `AUDTHM.DE` | etf | EUR | 30,00 | nessuna scheda, nessun metadato | unknown / etf |
| 9110 | `AUDUS.L` | etf | USD | 110,00 USD (101,20 €) | justETF «Equity, World», TER 0,20 | equity / etf |
| 9111 | `AUDUK.L` | etf | GBP | 10,00 GBP (11,70 €) | justETF «Bonds, United Kingdom, Government», TER 0,07; dividend_yield 3,0 | bond / etf |
| 9112 | `AUDSTL.MI` | etf | EUR | 60,00 (barra di 30 giorni fa) | justETF «Equity, Europe», TER 0,12 | equity / etf |
| 9113 | `AUDNPC.MI` | etf | EUR | 25,00 (una sola barra, oggi) | justETF «Equity, Emerging Markets», TER 0,18 | equity / etf |

Prezzi giornalieri: `AUDEQ.MI`, `AUDBD.MI`, `AUDTECH.DE`, `AUDUS.L`, `AUDUK.L` per gli ultimi 400
giorni; `AUDGOV.MI`, `AUDHY.DE`, `AUDBTP`, `AUDGLD.DE`, `AUDCMD.MI`, `AUDTHM.DE` solo per gli ultimi
30; `AUDSTL.MI` dal giorno −60 al −30. Storico degli stress test (≥ 2 barre in ciascuna finestra)
solo per gli strumenti di 9101:

| finestra | `AUDEQ.MI` | `AUDBD.MI` | `AUDTECH.DE` |
|---|---|---|---|
| Dot-Com Crash 2000-03-01…2002-10-31 | −40% | +12% | −70% |
| Global Financial Crisis 2007-10-01…2009-03-31 | −45% | +4% | −50% |
| Covid Crash 2020-02-19…2020-03-23 | −30% | −2% | −25% |
| Bear Market 2022 2022-01-03…2022-10-12 | −20% | −15% | −30% |

## Portafogli e valori documentati

Valori in EUR come li restituiscono `get_portfolio_summary` / `get_positions` (verificati dal test).

| id | nome | valore posizioni | liquidità | totale | posizioni: quantità × prezzo = valore (peso) |
|---|---|---|---|---|---|
| 9101 | AUD Bilanciato storico | 100.000,00 | 9.256,50 | 109.256,50 | `AUDEQ.MI` 700 × 100 = 70.000 (70,00); `AUDBD.MI` 400 × 50 = 20.000 (20,00); `AUDTECH.DE` 50 × 200 = 10.000 (10,00) |
| 9102 | AUD Solo obbligazioni | 42.350,00 | 8.144,00 | 50.494,00 | `AUDGOV.MI` 150 × 120 = 18.000 (42,50); `AUDHY.DE` 150 × 95 = 14.250 (33,65); `AUDBTP` 100 × 101 = 10.100 (23,85) |
| 9103 | AUD Oro e materie prime | 40.000,00 | 2.492,00 | 42.492,00 | `AUDGLD.DE` 400 × 40 = 16.000 (40,00); `AUDEQ.MI` 100 × 100 = 10.000 (25,00); `AUDCMD.MI` 400 × 20 = 8.000 (20,00); `AUDTHM.DE` 200 × 30 = 6.000 (15,00) |
| 9104 | AUD Londra e valute | 27.480,00 | 3.705,97 | 31.185,97 | `AUDUS.L` 100 × 101,20 = 10.120 (36,83); `AUDUK.L` 800 × 11,70 = 9.360 (34,06); `AUDEQ.MI` 80 × 100 = 8.000 (29,11) |
| 9105 | AUD Import | 15.000,00 | 5.545,00 | 20.545,00 | `AUDEQ.MI` 100 × 100 = 10.000 (66,67); `AUDBD.MI` 100 × 50 = 5.000 (33,33) |
| 9106 | AUD Vuoto | 0 | 0 | 0 | nessuna posizione, nessuna transazione, `cash_balance` 0 |
| 9107 | AUD Quotazioni ferme | 16.000,00 | 4.047,00 | 20.047,00 | `AUDSTL.MI` 100 × 60 = 6.000 (37,50, quotazione ferma); `AUDEQ.MI` 50 × 100 = 5.000 (31,25); `AUDNPC.MI` 200 × 25 = 5.000 (31,25, senza chiusura precedente) |
| aggregato | 9101…9107 | 240.830,00 | 33.190,47 | 274.020,47 | 13 strumenti; `AUDEQ.MI` in cinque portafogli (1.030 quote) |

Il totale coincide con `service_results.current_value` dell'export di performance (finestra 1y).

Transazioni (giorni prima di oggi):

- **9101**: deposito 100.000 (−300); acquisti `AUDEQ.MI` 750 × 90 (−290), `AUDBD.MI` 400 × 48
  (−285), `AUDTECH.DE` 50 × 180 (−280), commissioni 1,50; vendita `AUDEQ.MI` 50 × 98 (−60);
  dividendi EUR su `AUDTECH.DE` 30,00 (−200) e 32,50 (−20). Deposito, acquisti e vendita sono
  nell'ultimo anno (caso C1-TWR-MIXED). **Target** 50 / 40 / 10: oggi 70 / 20 / 10, quindi il
  ribilanciamento vende `AUDEQ.MI` (15.371,75) e compra `AUDBD.MI` e `AUDTECH.DE` (24.628,25) usando
  anche la liquidità (9.256,50): la sola liquidità non basta.
- **9102**: deposito 50.000 (−25); acquisti dei tre titoli (−24). Nessun target.
- **9103**: deposito 42.000 (−28); acquisti dei quattro strumenti (−27).
- **9104**: deposito 30.000 EUR (−200); `AUDUS.L` 100 × 105 USD (−190), `AUDUK.L` 800 × 9,80 GBP
  (−180), `AUDEQ.MI` 80 × 95 EUR (−170); dividendi GBP su `AUDUK.L` 40,00 (−90) e 42,00 (−10), EUR su
  `AUDEQ.MI` 15,00 (−60).
- **9105**: lotto d'import confermato in `csv_import_batches`; deposito 20.000 (−150); due acquisti
  identici `AUDEQ.MI` 50 × 96 (−140, esecuzione frazionata legittima), `AUDBD.MI` 100 × 49 (−140);
  dividendi EUR 12,00 su `AUDEQ.MI` a −120, −90, −60, −30 (stesso importo, date diverse).
- **9107**: deposito 20.000 (−60); `AUDSTL.MI` 100 × 61 (−55), `AUDEQ.MI` 50 × 99 (−50),
  `AUDNPC.MI` 200 × 24,50 (−5).

## Esiti attesi dai tool (sul codice corretto)

| area | valore |
|---|---|
| stress storici | 9101 `historical`, copertura 100%: GFC −35,7, Dot-Com −32,6, Covid −23,9, 2022 −20,0. 9102 `proxy` (copertura 0). 9103 `proxy` (copertura 25: solo `AUDEQ.MI` ha storico). Anche 9104 (29,11), 9107 (31,25) e l'aggregato (57,31) sono `proxy`; 9105 (`AUDEQ.MI` + `AUDBD.MI`) è `historical` |
| stress a shock | 9103: classi gold 40, equity 25, commodity 20, unknown 15 e flag `unknown_asset_class_equity_shock`; 9102: solo bond; 9101: `AUDTECH.DE` −45 nel crollo tech (moltiplicatore 1,5) |
| costi | 9101 TER medio 0,204, costo 204,00, copertura 100; 9102 `AUDHY.DE` 0,5 da yFinance (0,005 normalizzato), `AUDBTP` 0 dedotto; 9103 TER 0,227 su copertura 85,0, manca `AUDTHM.DE`; 9104 0,162; 9105 0,18; 9107 0,17 |
| reddito stimato | 9101 azionario 60,00; 9102 reddito fisso 1.324,10 (450 + 712,50 + 161,60); 9104 reddito fisso 280,80 |
| dividendi incassati | 9101 EUR 62,50 (2); 9104 EUR 15,00 (1) e GBP 82,00 (2), `mixed_currencies`; 9105 EUR 48,00 (4) |
| variazioni giornaliere | 9101: tre posizioni valide (`AUDEQ.MI` −0,28, `AUDBD.MI` −0,03, `AUDTECH.DE` +0,31); 9107: una valida (`AUDEQ.MI`), una ferma (`AUDSTL.MI`), una senza chiusura precedente (`AUDNPC.MI`) |
| performance 1y | 9101 TWR = MWR = 9,26%; 9104 3,95%; 9105 2,73% |
| Doctor (nessuna policy) | 9103 quota oro `lower` 40, azionaria `lower` 25; TER medio 0,23 (salute 0,23, costi 0,227) |
| vuoto | 9106: `positions` vuote, `scenarios` vuoti, liquidità 0 |

## Quale portafoglio esercita quale regola

La colonna «Prova» di `docs/auditor/rules.md` è riprodotta nella tabella `PROOF` del test, che per
ogni regola (52) verifica sul seed la precondizione per non andare in `skip`:

| portafoglio | casi |
|---|---|
| 9101 | stress storico (`historical`), crollo tech, ribilanciamento con vendite che finanziano acquisti, PAC, what-if, costi con copertura piena, reddito azionario, Monte Carlo, variazioni giornaliere, TWR/MWR con deposito e acquisti nella stessa finestra, X-Ray (pesi paese di `AUDEQ.MI`), Doctor |
| 9102 | stress `proxy`, solo obbligazioni, ETF obbligazionario tipizzato `stock` (`AUDHY.DE`), titolo `bond` diretto con TER dedotto 0, TER da yFinance in frazione, reddito fisso |
| 9103 | ETC sull'oro tipizzato `stock`, commodity, classe `unknown` senza TER (copertura parziale), quota oro del Doctor |
| 9104 | listing di Londra in USD e GBP, prezzi delle operazioni in valuta, dividendi in due valute |
| 9105 | lotto d'import confermato, coppia legittima di acquisti identici, dividendi mensili in una valuta |
| 9106 | portafoglio vuoto (`skip`/`empty_portfolio`, liquidità 0) |
| 9107 | quotazione ferma, posizione senza chiusura precedente, flag di qualità dei dati |
| aggregato 9101…9107 | somme e posizioni della vista aggregata, stress, Monte Carlo, X-Ray, salute, performance |

## Casi non riproducibili con un seed SQL

- **Import duplicato** (V-DUP-IMPORT, V365-009): il seed non passa dal flusso d'import CSV e
  `transactions` non registra il lotto. È rappresentato dal lotto confermato più la coppia legittima
  (nessun falso positivo atteso); il duplicato vero si riproduce nei test unitari di TASK-77.
- **Difetti dei finding** (prezzo per mille, pence letti come sterline, TER cento volte più piccolo,
  ETF obbligazionario `bond`): il seed rappresenta lo stato corretto dei dati, su cui le regole
  devono dare `pass`; i difetti si reintroducono nei test unitari delle regole.
- **Output troncato** (30 righe di `get_positions`, 20 di `get_cost_breakdown`): nessun portafoglio
  supera le 4 posizioni, `skip`/`truncated_output` non è esercitato dal seed.

## Agente settimanale (TASK-82)

```bash
scripts/auditor/agent_stack.sh start && eval "$(scripts/auditor/agent_stack.sh env)"
python3 scripts/auditor/mcp_call.py --list
python3 scripts/auditor/mcp_call.py get_cost_breakdown '{"portfolio_id": 9103}'
scripts/auditor/agent_stack.sh stop
```

Istruzioni complete, divieti e prompt della sessione programmata: `docs/auditor/agent-playbook.md` §2 e §7.
