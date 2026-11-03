# Retest MCP del 2026-11-03 — Analisi prima degli sviluppi

Documento sorgente: `backlog/docs/RETEST_MCP_2026-11-03.md` (chiamate MCP reali in sola lettura).
Le cause sono verificate sul codice di `main` dopo le PR #61–#67. La PR #68 (X-Ray) non era ancora mergiata al momento del retest.

## Sintesi

| Voce del retest | Esito della mia analisi | Serve sviluppo? |
|---|---|---|
| V365-001, 003, 004, 005, 006, 009, 010, 013 | Confermati risolti; coerenti con le correzioni attese | No |
| V365-002 — DBXP e VEUR `unknown` | **Riprodotto in locale** (vedi §1) | **Sì, P1** |
| V365-008 — Wealth: quantità, costi e TWR cambiati | **Tutte le variazioni sono spiegate** dalle correzioni dei dati e da TASK-46/49 (§2). Restano la riconciliazione con Fineco e TASK-41 (valuta dei `.L`) | Doc + dati del proprietario |
| V365-011 — tool aggregati non visibili nel client | Il codice li registra e i test li elencano: quasi certamente catalogo del connettore ChatGPT non aggiornato o deploy non allineato (§3) | Piccolo: versione esposta dal server |
| V365-012 — XAD1 `type=stock` | Confermato: `search_asset_info` restituisce il tipo tecnico senza la classe | **Sì, P2** (piccolo) |
| Quotazioni ferme al 2026-10-30 | Plausibile causa di configurazione dello scheduler (§5) | Indagine con query, poi decisione |
| X-Ray 0% su All Weather, TER mancanti | Manca la distinzione "non applicabile" / "dati mancanti"; mancano TER di ETF USA e VEUR | **Sì, P2** |
| Stress storici `method=proxy`, `coverage_pct=0` | Atteso: lo storico prezzi non copre 2008/2000/2020/2022. Comportamento documentato | No |

## 1. V365-002 — DBXP e VEUR classificati `unknown`

Riproduzione con `classify_asset` sui dati riportati dal retest:

| Simbolo | Nome in DB | Risultato |
|---|---|---|
| DBXP.DE | `XTR2 EGB13 1CC` (ISIN LU0290356871) | `unknown`, fonte `none` |
| VEUR | `Azioni Europa` | `unknown`, fonte `none` |
| XAD1.DE | `GOLD/DB ETC 60` | `gold` (corretto) |

**Cause:**
- I nomi sono abbreviazioni del broker (Fineco). Le regole per nome non conoscono `EGB` (Euro Government Bond) né la parola italiana `azioni`: la regola cerca solo `azionar`.
- Il classificatore riceve `investment_focus`, `index_tracked` e `category` dall'arricchimento justETF/yFinance. Se per questi ISIN l'arricchimento manca, non resta nessun segnale. Probabilmente manca, perché il retest mostra anche il TER di VEUR come mancante.
- Effetto: in "US Tech Crash" DBXP (6,39% di Parent) riceve −30% invece dello shock bond, cioè circa 2 punti di impatto sul portafoglio.

**Correzione proposta (preferendo dati strutturati, come chiede il retest):**
1. Classificare per ISIN tramite l'arricchimento justETF: se manca, recuperarlo e salvarlo (fonte verificabile).
2. Solo come fallback motivato, aggiungere parole chiave per i nomi abbreviati dei broker (`EGB`, `GOVT`, `TREAS`, `azioni`, `obblig`…) con test.
3. Test di accettazione: DBXP → bond e VEUR → equity in stress, reddito, X-Ray e health.

## 2. V365-008 — Le variazioni di Wealth sono spiegate

| Metrica | 2 nov | 3 nov | Causa |
|---|---|---|---|
| VWRA.L | 870,06 | 930,00 | +59,94: parte A (righe ×1000) |
| SE15.L | 477,03 | 506,00 | +28,97: parte A |
| IBTM.L | 49,04 | 92,00 | +42,96: parte A |
| EUN5.DE | 315,02 | 242,00 | +19,98 (parte A) − 93 (parte B, 3 acquisti duplicati da 31) |
| Costo di carico | 362.200,67 | 352.063,99 | −10.136,68: soprattutto i 3 acquisti EUN5 duplicati eliminati (≈ 3 × 3.692 €) |
| Valore posizioni | 417.257,89 | 433.791,57 | +16.533,68: quote mancanti ora valorizzate, meno le 93 EUN5 |
| Dividendi | 64 righe, 6.876,59 € | 46 righe, 4.121,72 € | parte B |
| TWR YTD / 1 anno | 20,22% / 35,22% | 5,63% / 7,64% | TASK-46: con i depositi di ottobre gli acquisti erano contati come rendimento |
| Liquidità | 819,59 € | 0 € | TASK-49: prima era depositi − prelievi + dividendi, senza acquisti e vendite |
| Apporti impliciti | — | 346.688,20 € | TASK-49: acquisti non coperti da depositi registrati (in Wealth risultano 2 depositi). Il valore è vicino al costo di carico, quindi coerente |

**Ancora da fare (non risolvibile dal codice):**
- **Confronto con Fineco**: quantità per strumento (gli importi attesi sono in `AUDIT_MCP_2026-11_VERIFICA.md`) e, se disponibile, il rendimento indicato dal broker.
- **TASK-41**: se VWRA.L, IBTM.L e SE15.L sono quotati in USD/GBP ma valorizzati come EUR, valore e rendimento di Parent e Wealth sono ancora distorti. È la verifica più importante rimasta.
- **TASK-45**: commissioni contate due volte (piccolo effetto sul costo).

## 3. V365-011 — Tool aggregati non visibili nel client ChatGPT

- `tools.py` registra i 9 tool `get_aggregate_*` in `EXPOSED_TOOL_NAMES`; i test di integrazione verificano che `tools/list` li contenga. Non esiste un'allowlist di tool configurabile da variabile d'ambiente (`MCP_ALLOWED_USER_IDS` filtra gli utenti, non i tool).
- **Cause probabili, nell'ordine:** (1) il connettore ChatGPT conserva il catalogo dei tool letto alla creazione, quindi va aggiornato o ricreato; (2) il deploy del backend non include la PR #63.
- **Proposta di sviluppo:** esporre nel server MCP la versione/commit (`serverInfo.version` e una riga nelle istruzioni), così un client può verificare quale versione sta interrogando.

## 4. V365-012 — XAD1 restituito come `stock`

`search_asset_info` riporta `asset_type` così come è salvato. Proposta, senza migrazione:
- aggiungere `asset_class` (dal classificatore condiviso), `instrument_type` (`etc`/`etn`/`etf`/`fund`/`stock`/`bond`, quando determinabile) e `classification_source`;
- descrivere nel tool quale campo usare per allocazione e rischio;
- test: XAD1, ETF azionario, ETF obbligazionario, ETN, azione singola.

## 5. Quotazioni ferme al 2026-10-30 (il 3 novembre)

Dal codice (`app/scheduler.py`, `pricing_service.refresh_prices`):
- lo scheduler aggiorna solo gli asset di `price_scheduler_portfolio_id` (**un solo portafoglio**, se configurato) e, se `enable_target_allocation` è attivo, **solo gli asset con un target**;
- di notte e nei fine settimana salta le borse chiuse (comportamento voluto);
- il refresh salva i *price tick*; la data `price_date` mostrata viene dalle barre giornaliere, popolate da un altro percorso.

Senza i dati non si può dire quale ramo è responsabile. Servono la configurazione dello scheduler su Render (`PRICE_SCHEDULER_ENABLED`, `PRICE_SCHEDULER_PORTFOLIO_ID`, `ENABLE_TARGET_ALLOCATION`) e la query Q10 sotto.

## 6. X-Ray e TER

- **X-Ray:** All Weather allo 0% e 100% Azionario al 14,2% sono in parte attesi: TLT, IEF, DJP e GLD non hanno top holdings azionarie e VEUR non ha arricchimento. Proposta: nell'output distinguere **"non applicabile"** (oro, materie prime, bond senza look-through) da **"dati mancanti"** e calcolare la copertura solo sulla parte applicabile, dichiarandolo.
- **TER mancanti:** TLT, IEF, DJP, GLD (ETF USA) e VEUR. Proposta: usare l'expense ratio di yFinance o di justETF quando c'è, sempre con `ter_source`.

## Query in sola lettura richieste (Supabase)

```sql
-- Q10: freschezza dei prezzi per gli asset dei portafogli 19 e 26
begin transaction read only;
select a.symbol,
       (select max(b.price_date) from price_bars_1d b where b.asset_id = a.id) as ultima_barra,
       (select max(t.ts) from price_ticks t where t.asset_id = a.id) as ultimo_tick
from assets a
where a.id in (select distinct asset_id from transactions where portfolio_id in (19, 26) and asset_id is not null)
order by ultima_barra nulls first, a.symbol;
rollback;

-- Q11: arricchimento disponibile per DBXP e VEUR
begin transaction read only;
select a.id, a.symbol, a.name, a.isin, a.asset_type,
       e.investment_focus, e.index_tracked, e.ter,
       m.category, m.expense_ratio
from assets a
left join etf_enrichment e on e.asset_id = a.id
left join asset_metadata m on m.asset_id = a.id
where a.symbol ilike 'DBXP%' or a.symbol ilike 'VEUR%' or a.symbol ilike 'XAD1%';
rollback;
```


## Piano proposto (da approvare)

| Priorità | Task | Contenuto |
|---|---|---|
| P1 | Classificazione DBXP/VEUR | arricchimento per ISIN, poi parole chiave di fallback, con test nei 4 consumer |
| P1 | TASK-41 | conferma della valuta dei listing `.L` da Fineco (blocca la riconciliazione di Wealth) |
| P2 | XAD1 in `search_asset_info` | `asset_class`, `instrument_type`, `classification_source` |
| P2 | Quote stale | Q10 e configurazione, poi correzione dello scheduler |
| P2 | X-Ray/TER | non applicabile vs mancante; TER da fonti verificabili |
| P3 | Versione MCP | versione/commit esposti dal server; aggiornamento del connettore ChatGPT a cura del proprietario |
